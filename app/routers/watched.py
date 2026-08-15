from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WatchedItem
from app.schemas import WatchedCreate, WatchedOut, WatchedUpdate
from app.services import activity

router = APIRouter(prefix="/api/watched", tags=["watched"])


@router.get("", response_model=list[WatchedOut])
def list_watched(db: Session = Depends(get_db)):
    return db.query(WatchedItem).order_by(WatchedItem.watched_date.desc()).all()


@router.post("", response_model=WatchedOut, status_code=201)
def create_watched(payload: WatchedCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    if data.get("watched_date") is None:
        data["watched_date"] = datetime.now(timezone.utc).date()

    item = WatchedItem(**data)
    db.add(item)
    db.commit()
    db.refresh(item)

    activity.log(db, "Marked as watched", item.title, "watched")
    return item


@router.patch("/{item_id}", response_model=WatchedOut)
def update_watched(item_id: str, payload: WatchedUpdate, db: Session = Depends(get_db)):
    item = db.get(WatchedItem, item_id)
    if not item:
        raise HTTPException(404, "Watched item not found")

    was_favorite = item.favorite
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)

    if payload.favorite is not None and payload.favorite != was_favorite:
        activity.log(
            db,
            "Marked favorite" if item.favorite else "Removed favorite",
            item.title,
            "favorite",
        )
    return item


@router.delete("/{item_id}", status_code=204)
def delete_watched(item_id: str, db: Session = Depends(get_db)):
    item = db.get(WatchedItem, item_id)
    if not item:
        raise HTTPException(404, "Watched item not found")
    db.delete(item)
    db.commit()
