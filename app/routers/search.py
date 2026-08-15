from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import MediaType, SearchResultOut
from app.services import tmdb

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=list[SearchResultOut])
def search(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return tmdb.search_multi(db, q)


@router.get("/details/{media_type}/{tmdb_id}")
def get_details(media_type: MediaType, tmdb_id: int, db: Session = Depends(get_db)):
    """Full TMDb detail lookup — used by the frontend to hydrate a search
    result (genres, runtime, director, cast) before adding it to the
    watchlist."""
    return tmdb.get_details(db, media_type, tmdb_id)
