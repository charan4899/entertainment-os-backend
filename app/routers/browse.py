from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WatchedItem, WatchlistItem
from app.schemas import BrowseResultOut, MediaType, WatchedOut
from app.services import activity, tmdb

router = APIRouter(prefix="/api/browse", tags=["browse"])


def _status_sets(db: Session) -> tuple[set[int], set[int]]:
    watched_ids = {row[0] for row in db.query(WatchedItem.tmdb_id).filter(WatchedItem.tmdb_id.isnot(None))}
    watchlist_ids = {row[0] for row in db.query(WatchlistItem.tmdb_id).filter(WatchlistItem.tmdb_id.isnot(None))}
    return watched_ids, watchlist_ids


@router.get("", response_model=list[BrowseResultOut])
def browse(
    media_type: MediaType = Query("movie"),
    query: str | None = Query(None, min_length=1),
    page: int = Query(1, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """No query -> paginated popular titles. With a query -> TMDb search,
    filtered to the requested media type. Either way, every result is
    flagged with whether it's already watched or queued."""
    watched_ids, watchlist_ids = _status_sets(db)

    if query:
        raw = [r for r in tmdb.search_multi(db, query, limit=40) if r["media_type"] == media_type]
    else:
        raw = tmdb.popular(db, media_type, page=page)

    return [
        BrowseResultOut(
            tmdb_id=item["tmdb_id"],
            title=item["title"],
            media_type=item["media_type"],
            year=item.get("year"),
            poster_path=item.get("poster_path"),
            imdb_rating=item.get("imdb_rating", 0.0),
            already_watched=item["tmdb_id"] in watched_ids,
            in_watchlist=item["tmdb_id"] in watchlist_ids,
        )
        for item in raw
    ]


@router.post("/{tmdb_id}/watched", response_model=WatchedOut, status_code=201)
def mark_watched(tmdb_id: int, media_type: MediaType = Query(...), db: Session = Depends(get_db)):
    """Directly log a title as watched from the Browse grid — no watchlist
    detour, for quickly building up watch history in bulk."""
    details = tmdb.get_details(db, media_type, tmdb_id)
    item = WatchedItem(
        tmdb_id=tmdb_id,
        title=details["title"],
        media_type=media_type,
        imdb_rating=details["imdb_rating"],
        genres=details["genres"],
        year=details["year"],
        watched_date=datetime.now(timezone.utc).date(),
        favorite=False,
        runtime_minutes=details["runtime_minutes"],
        seasons_watched=1 if media_type == "series" else None,
        poster_path=details["poster_path"],
        director=details["director"],
        cast=details["cast"],
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    activity.log(db, "Marked as watched", item.title, "watched")
    return item
