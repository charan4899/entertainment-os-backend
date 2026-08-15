"""
Recommendation logic — deliberately simple, no AI/ML APIs.

Cold start (fewer than COLD_START_THRESHOLD watched titles): surface TMDb's
top-rated movies and series, same as the Phase 1 seed data.

Once there's enough watch history: build a genre frequency profile from
what's been watched, then ask TMDb's /discover endpoint for highly-rated
titles in those genres, excluding anything already watched, queued, or
dismissed.
"""

from collections import Counter

from sqlalchemy.orm import Session

from app.models import AppSettings, IgnoredRecommendation, WatchedItem, WatchlistItem
from app.services import tmdb

COLD_START_THRESHOLD = 5


def _excluded_ids(db: Session) -> set[int]:
    watched_ids = {row[0] for row in db.query(WatchedItem.tmdb_id).filter(WatchedItem.tmdb_id.isnot(None))}
    watchlist_ids = {row[0] for row in db.query(WatchlistItem.tmdb_id).filter(WatchlistItem.tmdb_id.isnot(None))}
    ignored_ids = {row[0] for row in db.query(IgnoredRecommendation.tmdb_id)}
    return watched_ids | watchlist_ids | ignored_ids


def _get_settings(db: Session) -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _rank_score(rating: float, index: int) -> int:
    return max(1, min(99, round(rating * 10) - index))


def generate(db: Session, limit: int = 24) -> list[dict]:
    settings = _get_settings(db)
    exclude = _excluded_ids(db)
    watched = db.query(WatchedItem).all()

    media_types = []
    if settings.include_movies:
        media_types.append("movie")
    if settings.include_series:
        media_types.append("series")

    results: list[dict] = []

    if len(watched) < COLD_START_THRESHOLD:
        for media_type in media_types:
            for i, item in enumerate(tmdb.top_rated(db, media_type)):
                if item["tmdb_id"] in exclude:
                    continue
                if item["imdb_rating"] < settings.min_recommendation_rating:
                    continue
                results.append(
                    {
                        **item,
                        "reason": "Top-rated on TMDb — a great place to start your profile",
                        "match_score": _rank_score(item["imdb_rating"], i),
                    }
                )
    else:
        genre_counter: Counter[str] = Counter()
        for item in watched:
            genre_counter.update(item.genres or [])
        top_genres = [g for g, _ in genre_counter.most_common(3)]

        for media_type in media_types:
            reverse_map = {name: gid for gid, name in tmdb.genre_map(db, media_type).items()}
            genre_ids = [reverse_map[g] for g in top_genres if g in reverse_map]
            discovered = tmdb.discover(
                db,
                media_type,
                genre_ids,
                exclude,
                min_rating=settings.min_recommendation_rating,
                limit=limit,
            )
            for i, item in enumerate(discovered):
                overlap = [g for g in item.get("genres", []) if g in top_genres]
                reason = (
                    f"Matches your affinity for {overlap[0]}"
                    if overlap
                    else "Highly rated in genres you watch often"
                )
                results.append(
                    {**item, "reason": reason, "match_score": _rank_score(item["imdb_rating"], i)}
                )

    results.sort(key=lambda r: r["match_score"], reverse=True)
    return results[:limit]
