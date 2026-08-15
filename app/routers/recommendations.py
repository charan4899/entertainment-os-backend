from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import IgnoredRecommendation, WatchedItem, WatchlistItem
from app.schemas import MediaType, RecommendationOut, WatchedOut, WatchlistOut
from app.services import activity, tmdb
from app.services.recommendation_engine import generate

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=list[RecommendationOut])
def list_recommendations(db: Session = Depends(get_db)):
    return generate(db)


@router.post("/{tmdb_id}/ignore", status_code=204)
def ignore_recommendation(tmdb_id: int, media_type: MediaType = Query(...), db: Session = Depends(get_db)):
    db.add(IgnoredRecommendation(tmdb_id=tmdb_id, media_type=media_type))
    db.commit()


@router.post("/{tmdb_id}/watchlist", response_model=WatchlistOut, status_code=201)
def recommendation_to_watchlist(
    tmdb_id: int, media_type: MediaType = Query(...), db: Session = Depends(get_db)
):
    details = tmdb.get_details(db, media_type, tmdb_id)
    item = WatchlistItem(
        tmdb_id=tmdb_id,
        title=details["title"],
        media_type=media_type,
        imdb_rating=details["imdb_rating"],
        genres=details["genres"],
        year=details["year"],
        runtime_minutes=details["runtime_minutes"],
        poster_path=details["poster_path"],
        priority="medium",
        director=details["director"],
        cast=details["cast"],
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    activity.log(db, "Added to watchlist", item.title, "watchlist")
    return item


@router.post("/{tmdb_id}/watched", response_model=WatchedOut, status_code=201)
def recommendation_to_watched(
    tmdb_id: int, media_type: MediaType = Query(...), db: Session = Depends(get_db)
):
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
