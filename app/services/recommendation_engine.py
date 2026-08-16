"""
Recommendation logic — deliberately simple, no AI/ML APIs.

Three modes, in priority order:

1. Explicit filter active (genre and/or year picked on the page): always
   goes through /discover with those constraints, regardless of watch
   history. TMDb's top_rated endpoint has no date filter at all, so a year
   filter forces this path even with zero genres selected.

2. No filter, cold start (fewer than COLD_START_THRESHOLD watched titles):
   TMDb's top-rated movies and series.

3. No filter, enough watch history: genre-affinity /discover using your
   top 3 watched genres.

A page-level "show me only movies" / "only series" choice is orthogonal to
all three modes above — it just narrows which media type(s) get queried,
and each mode independently tries to fill the full requested count for
whichever type(s) are active, rather than splitting one shared pool.
"""

from collections import Counter

from sqlalchemy.orm import Session

from app.models import AppSettings, IgnoredRecommendation, WatchedItem, WatchlistItem
from app.services import tmdb

COLD_START_THRESHOLD = 5
DEFAULT_LIMIT = 50
MAX_PAGES_PER_TYPE = 8  # TMDb returns ~20 results/page
EXPLICIT_FILTER_MAX_PAGES = 20  # deliberate, occasional action — worth the extra calls

# TMDb's movie and TV genre lists use different names for what's really the
# same concept (e.g. movies have "Action", TV has "Action & Adventure").
# Selecting "Action" and then filtering to Series would otherwise silently
# resolve to zero genre ids for the TV lookup and return nothing. This maps
# a genre name to the names it should also be tried as in the *other*
# namespace.
_GENRE_ALIASES: dict[str, list[str]] = {
    "Action": ["Action & Adventure"],
    "Adventure": ["Action & Adventure"],
    "Action & Adventure": ["Action", "Adventure"],
    "Fantasy": ["Sci-Fi & Fantasy"],
    "Science Fiction": ["Sci-Fi & Fantasy"],
    "Sci-Fi & Fantasy": ["Fantasy", "Science Fiction"],
    "War": ["War & Politics"],
    "War & Politics": ["War"],
}


def _resolve_genre_ids(genre_names: list[str], reverse_map: dict[str, int]) -> list[int]:
    ids: list[int] = []
    for name in genre_names:
        if name in reverse_map:
            ids.append(reverse_map[name])
            continue
        for alias in _GENRE_ALIASES.get(name, []):
            if alias in reverse_map:
                ids.append(reverse_map[alias])
                break
    return ids


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


def generate(
    db: Session,
    limit: int = DEFAULT_LIMIT,
    genre_names: list[str] | None = None,
    min_year: int | None = None,
    media_type_filter: str | None = None,
) -> list[dict]:
    settings = _get_settings(db)
    exclude = _excluded_ids(db)
    watched = db.query(WatchedItem).all()

    # An explicit "only movies" / "only series" choice on the page overrides
    # the general Settings toggle for this request — it's a viewing choice,
    # not a change to your standing preference.
    media_types = [media_type_filter] if media_type_filter else _enabled_media_types(settings)

    results: list[dict] = []

    if genre_names or min_year:
        for media_type in media_types:
            reverse_map = {name: gid for gid, name in tmdb.genre_map(db, media_type).items()}
            genre_ids = _resolve_genre_ids(genre_names, reverse_map) if genre_names else []
            if genre_names and not genre_ids:
                # None of the selected genres exist in this media type's
                # namespace (even after aliasing) — nothing to fetch here,
                # move on rather than sending an unfiltered /discover call.
                continue

            discovered = tmdb.discover(
                db,
                media_type,
                genre_ids,
                exclude,
                min_rating=settings.min_recommendation_rating,
                min_year=min_year,
                limit=limit,
                max_pages=EXPLICIT_FILTER_MAX_PAGES,
            )
            for i, item in enumerate(discovered):
                overlap = [g for g in item.get("genres", []) if g in (genre_names or [])]
                if overlap:
                    reason = f"Matches your selected genre: {overlap[0]}"
                elif min_year:
                    reason = f"Released {min_year} or later"
                else:
                    reason = "Highly rated on TMDb"
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
            genre_ids = _resolve_genre_ids(top_genres, reverse_map)
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
