from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WatchedItem, WatchlistItem
from app.schemas import WatchedOut, WatchlistCreate, WatchlistOut
from app.services import activity, tmdb
from app.services.tmdb import TmdbError

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistOut])
def list_watchlist(db: Session = Depends(get_db)):
    return db.query(WatchlistItem).order_by(WatchlistItem.added_date.desc()).all()


@router.post("", response_model=WatchlistOut, status_code=201)
def create_watchlist_item(payload: WatchlistCreate, db: Session = Depends(get_db)):
    item = WatchlistItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)

    activity.log(db, "Added to watchlist", item.title, "watchlist")
    return item


@router.delete("/{item_id}", status_code=204)
def delete_watchlist_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(WatchlistItem, item_id)
    if not item:
        raise HTTPException(404, "Watchlist item not found")
    activity.log(db, "Removed from watchlist", item.title, "watchlist")
    db.delete(item)
    db.commit()


@router.post("/{item_id}/mark-watched", response_model=WatchedOut)
def mark_watched(item_id: str, db: Session = Depends(get_db)):
    item = db.get(WatchlistItem, item_id)
    if not item:
        raise HTTPException(404, "Watchlist item not found")

    # A watchlist row only stores whatever was known when it was added
    # (often just a season count of zero unknowns). Look up the current
    # season count from TMDb now, at the moment of marking watched, so
    # analytics and notifications have an accurate "seasons watched" figure
    # instead of defaulting to 1.
    seasons_watched = None
    if item.media_type == "series":
        seasons_watched = 1
        if item.tmdb_id:
            try:
                details = tmdb.get_details(db, "series", item.tmdb_id)
                seasons_watched = details.get("number_of_seasons") or 1
            except TmdbError:
                pass

    watched = WatchedItem(
        tmdb_id=item.tmdb_id,
        title=item.title,
        media_type=item.media_type,
        imdb_rating=item.imdb_rating,
        genres=item.genres,
        year=item.year,
        watched_date=datetime.now(timezone.utc).date(),
        favorite=False,
        runtime_minutes=item.runtime_minutes,
        seasons_watched=seasons_watched,
        poster_path=item.poster_path,
        director=item.director,
        cast=item.cast,
    )
    db.add(watched)
    db.delete(item)
    db.commit()
    db.refresh(watched)

    activity.log(db, "Marked as watched", watched.title, "watched")
    activity.log(db, "Recommendation engine refreshed", "Signal updated from new watch history", "system")
    return watched
