from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from models import User, SubjectCluster, ConceptCluster, InteractionSignal
from deps import get_db
from auth import get_current_user
from datetime import datetime, timedelta

router = APIRouter(prefix="/progress", tags=["progress"])

# ------------------------------------------------ Progress Endpoint ------------------------------------------------
@router.get("")
async def get_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return user's subject and concept cluster progress."""
    # Fetch subject clusters
    result = await db.execute(select(SubjectCluster).where(SubjectCluster.user_id == current_user.id))
    subjects = [
        {
            "subject": s.subject,
            "learning_skill": s.learning_skill,
            "last_updated": s.last_updated.isoformat(),
        }
        for s in result.scalars().all()
    ]
    # Fetch concept clusters
    result = await db.execute(select(ConceptCluster).where(ConceptCluster.user_id == current_user.id))
    concepts = [
        {
            "subject": c.subject,
            "name": c.name,
            "confidence": c.confidence,
            "last_seen": c.last_seen.isoformat(),
        }
        for c in result.scalars().all()
    ]
    return {"subjects": subjects, "concepts": concepts}

# ------------------------------------------------ Reflection Endpoint ------------------------------------------------
@router.get("/reflection")
async def get_reflection(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 7,
):
    """Return recent interaction signals and learning events (default: last 7 days)."""
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(InteractionSignal)
        .where(InteractionSignal.user_id == current_user.id, InteractionSignal.timestamp >= since)
        .order_by(desc(InteractionSignal.timestamp))
    )
    signals = [
        {
            "type": s.type,
            "timestamp": s.timestamp.isoformat(),
            "message_id": s.message_id,
        }
        for s in result.scalars().all()
    ]
    return {"signals": signals, "since": since.isoformat()}