import numpy as np
from datetime import datetime
from sqlalchemy import select
from models import SubjectCluster, ConceptCluster, InteractionSignal

# --- Embedding and similarity utilities ---
def get_embedding(text: str) -> np.ndarray:
    # Dummy embedding: replace with real model
    np.random.seed(abs(hash(text)) % (2**32))
    return np.random.rand(128)

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# --- Subject detection ---
def detect_subject(text: str) -> str:
    # Simple keyword-based subject detection: replace with real model
    text = text.lower()
    if any(w in text for w in ["math", "equation", "algebra", "geometry", "integral", "solve"]):
        return "Math"
    if any(w in text for w in ["physics", "force", "energy", "velocity", "acceleration"]):
        return "Science"
    if any(w in text for w in ["english", "grammar", "verb", "tense", "sentence"]):
        return "English"
    return "General"

# --- Interaction signal extraction ---
def extract_signals(text: str) -> list[str]:
    signals = []
    if any(w in text.lower() for w in ["why", "how", "can you explain", "what if"]):
        signals.append("follow_up")
    if any(w in text.lower() for w in ["oops", "sorry", "i meant", "correction"]):
        signals.append("self_correction")
    if any(w in text.lower() for w in ["like in math", "as in science", "similarly in"]):
        signals.append("cross_topic_transfer")
    return signals

# --- Main message processing ---
async def process_learning_message(db, user_id: int, message: str, message_id: int = None):
    subject = detect_subject(message)
    embedding = get_embedding(message)
    signals = extract_signals(message)
    now = datetime.utcnow()

    # --- Subject cluster ---
    result = await db.execute(select(SubjectCluster).where(SubjectCluster.user_id == user_id, SubjectCluster.subject == subject))
    subject_cluster = result.scalars().first()
    if not subject_cluster:
        subject_cluster = SubjectCluster(user_id=user_id, subject=subject, learning_skill="Weak", last_updated=now)
        db.add(subject_cluster)

    # --- Concept cluster matching ---
    result = await db.execute(select(ConceptCluster).where(ConceptCluster.user_id == user_id, ConceptCluster.subject == subject))
    clusters = result.scalars().all()
    best_sim = 0.0
    best_cluster = None
    for c in clusters:
        c_emb = np.fromstring(c.embedding, sep=",")
        sim = cosine_similarity(embedding, c_emb)
        if sim > best_sim:
            best_sim = sim
            best_cluster = c
    # Threshold for new cluster
    if best_sim > 0.85 and best_cluster:
        # Update existing cluster
        best_cluster.last_seen = now
        best_cluster.confidence = increment_confidence(best_cluster.confidence)
        # Optionally update name
    else:
        # Create new cluster
        new_cluster = ConceptCluster(
            user_id=user_id,
            subject=subject,
            embedding=",".join(map(str, embedding.tolist())),
            name=None,
            confidence="Weak",
            last_seen=now
        )
        db.add(new_cluster)

    # --- Update subject learning skill ---
    if signals:
        subject_cluster.learning_skill = increment_confidence(subject_cluster.learning_skill)
    subject_cluster.last_updated = now

    # --- Store interaction signals ---
    for sig in signals:
        db.add(InteractionSignal(user_id=user_id, type=sig, timestamp=now, message_id=message_id))

    await db.commit()
    return subject_cluster, signals

def increment_confidence(current: str) -> str:
    if current == "Weak":
        return "Improving"
    if current == "Improving":
        return "Strong"
    return "Strong"