from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WatchedItem
from app.schemas import AnalyticsOut, GenreCount, NameCount, YearCount

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Same assumption used on the frontend dashboard: Phase 1/2 has no per-episode
# TMDb data wired into watch-time yet, so series minutes are estimated at
# ~10 episodes per tracked season.
ASSUMED_EPISODES_PER_SEASON = 10


@router.get("", response_model=AnalyticsOut)
def get_analytics(db: Session = Depends(get_db)):
    items = db.query(WatchedItem).all()

    movies_watched = sum(1 for i in items if i.media_type == "movie")
    series_watched = sum(1 for i in items if i.media_type == "series")

    total_minutes = 0
    genre_counter: Counter[str] = Counter()
    year_counter: Counter[int] = Counter()
    director_counter: Counter[str] = Counter()
    actor_counter: Counter[str] = Counter()

    for item in items:
        if item.media_type == "movie":
            total_minutes += item.runtime_minutes
        else:
            episodes = (item.seasons_watched or 1) * ASSUMED_EPISODES_PER_SEASON
            total_minutes += item.runtime_minutes * episodes

        genre_counter.update(item.genres or [])
        if item.year:
            year_counter[item.year] += 1
        if item.director:
            director_counter[item.director] += 1
        actor_counter.update(item.cast or [])

    genre_distribution = [GenreCount(genre=g, count=c) for g, c in genre_counter.most_common()]
    release_year_distribution = [
        YearCount(year=y, count=c) for y, c in sorted(year_counter.items())
    ]
    top_genres = [GenreCount(genre=g, count=c) for g, c in genre_counter.most_common(5)]
    top_directors = [NameCount(name=n, count=c) for n, c in director_counter.most_common(5)]
    top_actors = [NameCount(name=n, count=c) for n, c in actor_counter.most_common(5)]

    return AnalyticsOut(
        movies_watched=movies_watched,
        series_watched=series_watched,
        total_watch_minutes=total_minutes,
        genre_distribution=genre_distribution,
        release_year_distribution=release_year_distribution,
        top_genres=top_genres,
        top_directors=top_directors,
        top_actors=top_actors,
    )
