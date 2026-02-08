from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import User, SubjectCluster, ConceptCluster
from deps import get_db
from auth import get_current_user

router = APIRouter(prefix="/progress", tags=["progress"])

# ------------------------------------------------ Progress Endpoint ------------------------------------------------
@router.get("")
async def get_progress(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Return user's subject and concept cluster progress, including deltas."""

    # Fetch Subject Clusters
    result = await db.execute(select(SubjectCluster).where(SubjectCluster.user_id == current_user.id))
    subjects_raw = result.scalars().all()

    # Fetch Concept Clusters
    result = await db.execute(select(ConceptCluster).where(ConceptCluster.user_id == current_user.id))
    concepts_raw = result.scalars().all()

    # Group concepts by subject
    concepts_by_subject = {}
    for c in concepts_raw:
        concepts_by_subject.setdefault(c.subject, []).append({
            "name": c.name,
            "confidence": c.confidence,
            "confidence_score": c.confidence_score,
            "confidence_delta": c.confidence_delta,
            "last_seen": c.last_seen.isoformat() if c.last_seen else None,
            "delta_since": c.delta_since.isoformat() if c.delta_since else None,
        })

    # Build subject-level view including concepts
    subjects = []
    for s in subjects_raw:
        subjects.append({
            "subject": s.subject,
            "learning_skill": s.learning_skill,
            "learning_delta": s.learning_delta,
            "last_updated": s.last_updated.isoformat() if s.last_updated else None,
            "delta_since": s.delta_since.isoformat() if s.delta_since else None,
            "concepts": concepts_by_subject.get(s.subject, [])
        })

    return {"subjects": subjects}