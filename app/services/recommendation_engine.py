"""
Recommendation logic — deliberately simple, no AI/ML APIs.

Cold start (fewer than COLD_START_THRESHOLD watched titles): surface TMDb's
top-rated movies and series, same as the Phase 1 seed data.

Once there's enough watch history: build a genre frequency profile from
what's been watched, then ask TMDb's /discover endpoint for highly-rated
titles in those genres, excluding anything already watched, queued, or
dismissed.

If the person explicitly picks genres on the Recommendations page, that
takes priority over both of the above — it's a deliberate, explicit ask,
so it always goes through /discover with a higher page budget to actually
try to fill the requested count.
"""

from collections import Counter

from sqlalchemy.orm import Session

from app.models import AppSettings, IgnoredRecommendation, WatchedItem, WatchlistItem
from app.services import tmdb

COLD_START_THRESHOLD = 5
DEFAULT_LIMIT = 50
MAX_PAGES_PER_TYPE = 8  # TMDb returns ~20 results/page
GENRE_FILTER_MAX_PAGES = 20  # explicit, deliberate ask — worth the extra calls


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


def _enabled_media_types(settings: AppSettings) -> list[str]:
    media_types = []
    if settings.include_movies:
        media_types.append("movie")
    if settings.include_series:
        media_types.append("series")
    return media_types


def available_genres(db: Session) -> list[str]:
    """Genre names the filter UI can offer — union of whichever media
    types are enabled, minus Documentary (always excluded from
    recommendations regardless of filter)."""
    settings = _get_settings(db)
    names: set[str] = set()
    for media_type in _enabled_media_types(settings) or ["movie", "series"]:
        names.update(tmdb.genre_map(db, media_type).values())
    names.discard("Documentary")
    return sorted(names)


def generate(db: Session, limit: int = DEFAULT_LIMIT, genre_names: list[str] | None = None) -> list[dict]:
    settings = _get_settings(db)
    exclude = _excluded_ids(db)
    watched = db.query(WatchedItem).all()
    media_types = _enabled_media_types(settings)

    results: list[dict] = []

    if genre_names:
        # Explicit filter — always goes through /discover, regardless of
        # watch history, with a much higher page budget since this is a
        # deliberate one-off request rather than a background refill.
        for media_type in media_types:
            reverse_map = {name: gid for gid, name in tmdb.genre_map(db, media_type).items()}
            genre_ids = [reverse_map[g] for g in genre_names if g in reverse_map]
            if not genre_ids:
                continue
            discovered = tmdb.discover(
                db,
                media_type,
                genre_ids,
                exclude,
                min_rating=settings.min_recommendation_rating,
                limit=limit,
                max_pages=GENRE_FILTER_MAX_PAGES,
            )
            for i, item in enumerate(discovered):
                overlap = [g for g in item.get("genres", []) if g in genre_names]
                reason = (
                    f"Matches your selected genre: {overlap[0]}"
                    if overlap
                    else f"Highly rated — tagged under {', '.join(item.get('genres', [])[:2]) or 'your selection'}"
                )
                results.append(
                    {**item, "reason": reason, "match_score": _rank_score(item["imdb_rating"], i)}
                )

    elif len(watched) < COLD_START_THRESHOLD:
        # Pull as many top-rated pages as needed (per type) so that after
        # excluding watched/queued/ignored titles we still have enough left
        # to fill the requested limit, rather than stopping at page 1.
        per_type_target = limit  # worst case: all results end up in one type
        for media_type in media_types:
            collected = 0
            for page in range(1, MAX_PAGES_PER_TYPE + 1):
                page_items = tmdb.top_rated(db, media_type, page=page)
                if not page_items:
                    break
                for item in page_items:
                    if item["tmdb_id"] in exclude:
                        continue
                    if item["imdb_rating"] < settings.min_recommendation_rating:
                        continue
                    results.append(
                        {
                            **item,
                            "reason": "Top-rated on TMDb — a great place to start your profile",
                            "match_score": _rank_score(item["imdb_rating"], collected),
                        }
                    )
                    collected += 1
                if collected >= per_type_target:
                    break
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
                max_pages=MAX_PAGES_PER_TYPE,
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
