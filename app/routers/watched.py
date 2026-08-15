from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WatchedItem
from app.schemas import (
    BackfillSeasonsItem,
    BackfillSeasonsResult,
    WatchedCreate,
    WatchedOut,
    WatchedUpdate,
)
from app.services import activity, tmdb
from app.services.tmdb import TmdbError

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


@router.post("/backfill-seasons", response_model=BackfillSeasonsResult)
def backfill_seasons(db: Session = Depends(get_db)):
    """
    One-off maintenance action: earlier versions of the "mark watched"
    endpoints hardcoded seasons_watched=1 regardless of a show's real season
    count. This re-fetches the current season count from TMDb for every
    watched series and corrects it. Safe to run more than once — anything
    already correct is left alone and reported as unchanged.
    """
    candidates = (
        db.query(WatchedItem)
        .filter(WatchedItem.media_type == "series", WatchedItem.tmdb_id.isnot(None))
        .all()
    )

    updated: list[BackfillSeasonsItem] = []
    unchanged_count = 0
    skipped_count = 0

    for item in candidates:
        try:
            details = tmdb.get_details(db, "series", item.tmdb_id)
        except TmdbError:
            skipped_count += 1
            continue

        real_count = details.get("number_of_seasons") or 1
        if item.seasons_watched == real_count:
            unchanged_count += 1
            continue

        updated.append(
            BackfillSeasonsItem(
                title=item.title,
                previous_seasons_watched=item.seasons_watched,
                new_seasons_watched=real_count,
            )
        )
        item.seasons_watched = real_count

    if updated:
        db.commit()
        activity.log(
            db,
            "Season counts backfilled",
            f"{len(updated)} show(s) corrected",
            "system",
        )

    return BackfillSeasonsResult(
        updated=updated,
        unchanged_count=unchanged_count,
        skipped_count=skipped_count,
    )


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
    title = item.title
    db.delete(item)
    db.commit()
    activity.log(db, "Removed from watched", title, "watched")
