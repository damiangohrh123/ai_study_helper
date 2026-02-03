"""
This module implements the core learning-tracking logic for the AI study helper.

Key concepts:

- Interaction Signals: Indicators extracted from a user's message that suggest engagement or learning activity.
  Examples:
    - follow_up             → user asks "why", "how", or "what if"
    - self_correction       → user corrects themselves ("oops", "i meant")
    - cross_topic_transfer  → user links concepts across subjects ("like in math")

- Concept Clusters: Groupings of similar ideas or concepts a user has learned, tracked per user.
  Each cluster has:
    - an embedding (vector) representing its semantic content
    - a confidence score indicating the user's mastery level

- Confidence: Numeric score per cluster, mapped to "Weak", "Improving", "Strong".
  Cluster scores are updated based on signals and decay over time.
  Subject-level confidence is computed as the average of all clusters under that subject.
"""

import os
import asyncio
import numpy as np
import json
import re
from datetime import datetime, timezone
from sqlalchemy import select

from models import SubjectCluster, ConceptCluster, InteractionSignal
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# ------------------------------------------------ Globals ------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Embedding model for turning text into numeric vectors
EMBEDDER = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=OPENAI_API_KEY,
)

# LLM for classifying subject and generating short concept names
LLM = ChatOpenAI(
    model="gpt-3.5-turbo",
    temperature=0,
    openai_api_key=OPENAI_API_KEY,
)

SUBJECTS = {"Math", "Science", "English", "General"}

SIMILARITY_THRESHOLD = 0.85
DECAY_PER_DAY = 0.1
MAX_SIGNAL_GAIN = 3.0

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
async def classify_and_name(message: str) -> tuple[str, str]:
    """
    Classify a message into a subject and generate a short concept name.
    Returns:
        subject (str): One of Math, Science, English, General
        concept_name (str | None): concise concept name (max 32 chars)
    """

    if not message or not message.strip():
        return "General", None

    system_prompt = SystemMessage(
        content=(
            "You are an educational assistant.\n"
            "1) Classify the subject as one of: Math, Science, English, General.\n"
            "2) Generate a concise concept name (max 5 words).\n\n"
            "Respond ONLY in valid JSON like:\n"
            '{ "subject": "Math", "concept_name": "Linear equations" }'
        )
    )

    user_prompt = HumanMessage(content=message[:500])  # Safety cap

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
        pass  # fall back to defaults

    if subject not in SUBJECTS:
        subject = "General"

    return subject, concept_name

# --------------------------------- Interaction signal extraction ---------------------------------
def extract_signals(text: str) -> list[str]:
    """
    Extract interaction signals from user message.
    Signals indicate engagement or learning activity that can update confidence.
    """
    signals = []
    if any(w in text.lower() for w in ["why", "how", "can you explain", "what if"]):
        signals.append("follow_up")
    if any(w in text.lower() for w in ["oops", "sorry", "i meant", "correction"]):
        signals.append("self_correction")
    if any(w in text.lower() for w in ["like in math", "as in science", "similarly in"]):
        signals.append("cross_topic_transfer")
    return signals

# ---------------------------------  Confidence Logic ---------------------------------
SIGNAL_WEIGHTS = {
    "follow_up": 1,
    "self_correction": 2,
    "cross_topic_transfer": 1,
}

def update_confidence_score(current_score: float, signals: list[str]) -> float:
    gain = sum(SIGNAL_WEIGHTS.get(s, 0) for s in signals)
    return current_score + min(gain, MAX_SIGNAL_GAIN)

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
def update_concept_confidence(cluster, signals: list[str], now: datetime):
    days_passed = (now - cluster.last_seen).days

    if days_passed > 1:
        cluster.confidence_score = max(0, cluster.confidence_score - DECAY_PER_DAY * days_passed)

    cluster.confidence_score = update_confidence_score(cluster.confidence_score, signals)
    cluster.confidence = score_to_confidence(cluster.confidence_score)
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

    # 1. Get embeddings and signals
    embedding = await get_embedding(message)
    signals = extract_signals(message)

    # 2. Load user's concept clusters
    result = await db.execute(select(ConceptCluster).where(ConceptCluster.user_id == user_id))
    clusters = result.scalars().all()

    # 3. Find best matching cluster
    best_cluster, similarity = find_best_cluster(embedding, clusters)

    if best_cluster and similarity > SIMILARITY_THRESHOLD:
        update_concept_confidence(best_cluster, signals, now)
        subject = best_cluster.subject
    else:
        # New concept → classify
        subject, name = await classify_and_name(message)
        initial_score = 0.5 + sum(SIGNAL_WEIGHTS.get(s, 0) for s in signals)

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

    # 6. Store interaction signals
    db.add_all([
        InteractionSignal(
            user_id=user_id,
            type=sig,
            timestamp=now,
            message_id=message_id
        )
        for sig in signals
    ])

    # 7. Commit all changes
    await db.commit()
    
    return subject_cluster, signals