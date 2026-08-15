from sqlalchemy.orm import Session

from app.models import ActivityEvent


def log(db: Session, label: str, detail: str, kind: str) -> None:
    db.add(ActivityEvent(label=label, detail=detail, kind=kind))
    db.commit()
