from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ActivityEvent
from app.schemas import ActivityOut

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("", response_model=list[ActivityOut])
def list_activity(db: Session = Depends(get_db)):
    return db.query(ActivityEvent).order_by(ActivityEvent.timestamp.desc()).limit(20).all()
