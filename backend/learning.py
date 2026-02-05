"""
This module implements the core learning-tracking logic for the AI study helper.

Key concepts:

- Concept Clusters: Groupings of similar ideas or concepts a user has learned, tracked per user.
    Each cluster has:
        - an embedding (vector) representing its semantic content
        - a confidence score indicating the user's mastery level

- Confidence: Numeric score per cluster, mapped to "Weak", "Improving", "Strong".
    Cluster scores are updated using pattern-based logic (review frequency, time spacing, semantic similarity, and cross-topic links) and decay over time.
    Subject-level confidence is computed as the average of all clusters under that subject.
"""

import os
import asyncio
import numpy as np
import json
import re
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from typing import List

from models import SubjectCluster, ConceptCluster
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Embedding model for turning text into numeric vectors
EMBEDDER = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=OPENAI_API_KEY,
)

# LLM for classifying subject and generating short concept names
LLM = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=OPENAI_API_KEY,
)

SUBJECTS = {"Math", "Science", "English", "General"}

SIMILARITY_THRESHOLD = 0.85
DECAY_PER_DAY = 0.1

# ------------------------------------------------ Embeddings ------------------------------------------------
async def get_embedding(text: str) -> np.ndarray:
    """
    Get an embedding vector for the given text using OpenAI.

    Why async? 
    - EMBEDDER.embed_query is synchronous (blocking). If called directly in an async app, 
      it would freeze the event loop.
    - Using loop.run_in_executor runs embed_query in a background thread, so other async tasks can continue while waiting.
    """
    loop = asyncio.get_running_loop()
    emb = await loop.run_in_executor(None, EMBEDDER.embed_query, text)

    vec = np.array(emb, dtype=np.float32) # Cast to float32 for consistency
    norm = np.linalg.norm(vec)

    if norm == 0:
        return vec  # extremely unlikely, but safe

    return vec / norm

# ------------------------------------------------ Subject detection ------------------------------------------------
async def classify_subject_and_concept(message: str) -> tuple[str, str]:
    """
    Use a single LLM call to extract subject and concept name from a message.
    Returns: (subject, concept_name)
    """
    if not message or not message.strip():
        return "General", None

    system_prompt = SystemMessage(
        content=(
            "You are an educational assistant.\n"
            "Given a user's message, do all of the following in one JSON object:\n"
            "1) Classify the subject as one of: Math, Science, English, General.\n"
            "2) Generate a concise concept name (max 5 words).\n"
            "Respond ONLY in valid JSON like:\n"
            '{ "subject": "Math", "concept_name": "Linear equations" }\n'
        )
    )
    user_prompt = HumanMessage(content=message[:500])

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None, lambda: LLM.invoke([system_prompt, user_prompt])
    )

    subject = "General"
    concept_name = None
    try:
        match = re.search(r"\{.*\}", response.content, flags=re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            subject = data.get("subject", subject)
            concept_name = data.get("concept_name")
    except Exception:
        pass
    if subject not in SUBJECTS:
        subject = "General"
    return subject, concept_name

def score_to_confidence(score: float) -> str:
    if score < 3:
        return "Weak"
    if score < 5:
        return "Improving"
    return "Strong"

# ------------------------------------------------ Similarity matching ------------------------------------------------
def find_best_cluster(embedding: np.ndarray, clusters: list) -> tuple[object | None, float]:
    if not clusters:
        return None, 0.0

    vectors = np.array([
        np.frombuffer(c.embedding, dtype=np.float32) for c in clusters
    ])

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)  # compute L2 norm of each vector
    norms[norms == 0] = 1                                   # avoid division by zero by making 0 values equal 1
    vectors /= norms                                        # normalize vectors to unit length

    sims = vectors @ embedding

    idx = int(np.argmax(sims))
    return clusters[idx], float(sims[idx])

# ------------------------------------------------ Concept confidence update ------------------------------------------------
def update_concept_confidence(cluster, now: datetime):
    days_passed = (now - cluster.last_seen).days

    if days_passed > 1:
        cluster.confidence_score = max(0, cluster.confidence_score - DECAY_PER_DAY * days_passed)

    # Pattern-based confidence update logic would go here
    cluster.last_seen = now

# ------------------------------------------------ Subject confidence update ------------------------------------------------
def recompute_subject_confidence(subject_cluster, clusters: list, subject: str, best_cluster=None):
    """
    Recompute the subject-level confidence based on all clusters under the subject.
    Ensures best_cluster is included once without double-counting.
    """
    relevant = [
        c for c in clusters
        if c.subject == subject and c is not best_cluster
    ]

    if best_cluster and best_cluster.subject == subject:
        relevant.append(best_cluster)

    if not relevant:
        return

    avg_score = sum(c.confidence_score for c in relevant) / len(relevant)
    subject_cluster.learning_skill = score_to_confidence(avg_score)

# --------------------------------- Main message processing ---------------------------------
async def process_learning_message(db, user_id: int, message: str, message_id: int = None):
    now = datetime.now(timezone.utc)

    # 1. Get embeddings
    embedding = await get_embedding(message)

    # 2. Load user's concept clusters
    result = await db.execute(select(ConceptCluster).where(ConceptCluster.user_id == user_id))
    clusters = result.scalars().all()

    # 3. Find best matching cluster
    best_cluster, similarity = find_best_cluster(embedding, clusters)

    if best_cluster and similarity > SIMILARITY_THRESHOLD:
        update_concept_confidence(best_cluster, now)
        subject = best_cluster.subject
        concept_name = best_cluster.name
    else:
        # New concept → classify subject and concept name in one call
        subject, name = await classify_subject_and_concept(message)
        initial_score = 0.5  # Pattern-based scoring can be added here

        best_cluster = ConceptCluster(
            user_id=user_id,
            subject=subject,
            embedding=embedding.tobytes(),
            confidence_score=initial_score,
            confidence=score_to_confidence(initial_score),
            last_seen=now,
            name=(name or "Concept")[:32],
        )
        db.add(best_cluster)
        concept_name = best_cluster.name

    # Logging input, subject, and concept
    logging.info(f"Input: {message} | Subject: {subject} | Concept: {concept_name}")

    # 4. Load or create subject cluster
    result = await db.execute(
        select(SubjectCluster).where(
            SubjectCluster.user_id == user_id,
            SubjectCluster.subject == subject,
        )
    )
    subject_cluster = result.scalars().first()

    if not subject_cluster:
        subject_cluster = SubjectCluster(
            user_id=user_id,
            subject=subject,
            learning_skill="Weak",
            last_updated=now,
        )
        db.add(subject_cluster)

    # 5. Update subject confidence
    recompute_subject_confidence(subject_cluster, clusters, subject, best_cluster=best_cluster)
    subject_cluster.last_updated = now

    # 6. Commit all changes
    await db.commit()
    
    return subject_cluster