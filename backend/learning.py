"""
This module implements the core learning-tracking logic for the AI study helper.

Key concepts:

- Concept Clusters: Groupings of similar ideas or concepts a user has learned, tracked per user.
    Each cluster has:
        - an embedding (vector) representing its semantic content
        - a confidence score indicating the user's mastery level

- Confidence: Numeric score per cluster, mapped to "Weak", "Improving", "Strong".
    Cluster scores are updated using pattern-based logic (review frequency, time spacing, semantic similarity) and decay over time.
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
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from models import SubjectCluster, ConceptCluster
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# ------------------------------------------------ Configuration ------------------------------------------------
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
MAX_CONFIDENCE = 6.0

# ------------------------------------------------ Utilities ------------------------------------------------
def score_to_confidence(score: float) -> str:
    if score < 3:
        return "Weak"
    if score < 5:
        return "Improving"
    return "Strong"

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

    return vec if norm == 0 else vec / norm

# ------------------------------------------------ Subject detection ------------------------------------------------
async def classify_subject_and_concept(message: str) -> tuple[str, Optional[str]]:
    """
    Use a single LLM call to extract subject and concept name from a message.
    Returns: (subject, concept_name)
    """
    if not message.strip():
        return "General", None

    system_prompt = SystemMessage(
        content=(
            "Classify the subject and name the concept.\n"
            "Subjects: Math, Science, English, General.\n"
            "Return JSON only:\n"
            '{ "subject": "Math", "concept_name": "Linear equations" }\n'
        )
    )

    user_prompt = HumanMessage(content=message[:500])

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None, lambda: LLM.invoke([system_prompt, user_prompt])
    )

    try:
        match = re.search(r"\{.*\}", response.content, re.DOTALL)
        if match:
            data = json.loads(match.group())
            subject = data.get("subject", "General")
            concept = data.get("concept_name")
        else:
            subject, concept = "General", None
    except Exception:
        subject, concept = "General", None

    return (subject if subject in SUBJECTS else "General"), concept

# ------------------------------------------------ Similarity matching ------------------------------------------------
def find_best_cluster(embedding: np.ndarray, clusters: list[ConceptCluster]) -> tuple[Optional[ConceptCluster], float]:
    """
    Return the most similar ConceptCluster and its cosine similarity score.
    """
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
def update_concept_confidence(cluster: ConceptCluster, similarity: float, now: datetime) -> None:
    """
    Pattern-based confidence update:
    - decay
    - revisit reinforcement
    - semantic strength
    - spacing bonus
    """
    days = (now - cluster.last_seen).days

    # 1. Decay
    cluster.confidence_score = max(0.0, cluster.confidence_score - DECAY_PER_DAY * days)

    # 2. Reinforcement by revisit, and similarity boost
    cluster.confidence_score += 0.5
    cluster.confidence_score += similarity * 0.8

    # 3. Spacing bonus (if revisited after 2-14 days)
    if 2 <= days <= 14:
        cluster.confidence_score += 1.0

    # 4. Soft cap + update confidence level + record time of this interaction
    cluster.confidence_score = min(cluster.confidence_score, MAX_CONFIDENCE)
    cluster.confidence = score_to_confidence(cluster.confidence_score)
    cluster.last_seen = now

# ------------------------------------------------ Subject confidence update ------------------------------------------------
async def recompute_subject_confidence(db: AsyncSession, user_id: int, subject: str, clusters: Optional[list[ConceptCluster]] = None) -> Optional[SubjectCluster]:
    """
    Recompute or create the subject-level confidence for a user.

    - If clusters are provided, only those are used.
    - Otherwise, fetch all clusters for this user and subject from the DB.
    """
    
    # 1. If clusters not provided, fetch them
    if clusters is None:
        result = await db.execute(
            select(ConceptCluster).where(
                ConceptCluster.user_id == user_id,
                ConceptCluster.subject == subject
            )
        )
        clusters = result.scalars().all()

    if not clusters:
        return None

    # 2. Compute average confidence score across all clusters
    avg_score = sum(c.confidence_score for c in clusters) / len(clusters)

    # 3. Fetch the SubjectCluster, if it exists
    result = await db.execute(
        select(SubjectCluster).where(
            SubjectCluster.user_id == user_id,
            SubjectCluster.subject == subject
        )
    )
    subject_cluster = result.scalars().first()

    if subject_cluster:
        subject_cluster.learning_skill = score_to_confidence(avg_score)
    else:
        subject_cluster = SubjectCluster(
            user_id=user_id,
            subject=subject,
            learning_skill=score_to_confidence(avg_score)
        )
        db.add(subject_cluster)

    return subject_cluster

# --------------------------------- Main message processing ---------------------------------
async def process_learning_message(db: AsyncSession, user_id: int, message: str) -> Optional[SubjectCluster]:
    """
    Main learning pipeline (optimized):
    1. Embed message
    2. Determine subject & concept
    3. Load only relevant subject clusters
    4. Match or create concept cluster
    5. Update concept confidence
    6. Recompute subject confidence
    7. Commit changes
    """
    # If message is empty, skip processing
    if not message.strip():
        return None
    
    now = datetime.now(timezone.utc)

    # 1. Get embeddings
    embedding = await get_embedding(message)

    # 2. Classify subject and concept name first
    subject, name = await classify_subject_and_concept(message)

    # 3. Load clusters only for this subject
    result = await db.execute(
        select(ConceptCluster).where(
            ConceptCluster.user_id == user_id,
            ConceptCluster.subject == subject
        )
    )
    subject_clusters = result.scalars().all()

    # 4. Find the best cluster among this subject
    best_cluster, similarity = find_best_cluster(embedding, subject_clusters)

    # 5. Update existing cluster or create new one
    if best_cluster and similarity > SIMILARITY_THRESHOLD:
        update_concept_confidence(best_cluster, similarity, now)
        concept_name = best_cluster.name
    else:
        # Use similarity even if below threshold for initial score
        initial_score = 0.5 + (similarity * 0.5)
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
        subject_clusters.append(best_cluster)  # include new cluster for recompute
        concept_name = best_cluster.name

    logging.info(f"Input: {message} | Subject: {subject} | Concept: {concept_name}")

    # 6. Recompute subject confidence (handles creation/update)
    subject_cluster = await recompute_subject_confidence(db, user_id, subject, subject_clusters)

    # 7. Commit everything
    await db.commit()
    return subject_cluster