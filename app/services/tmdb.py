"""
Thin TMDb API client.

Important: TMDb's free API does not expose IMDb's own rating — that would
require OMDb (a separate service). We use TMDb's `vote_average` (also a
0-10 scale, community-voted) as the closest free equivalent, and keep it in
the `imdb_rating` field name throughout the app for continuity with the
Phase 1 frontend. If true IMDb ratings matter to you, swap this service for
one that calls OMDb using the title/year as a lookup key.
"""

from datetime import date

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AppSettings

TMDB_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

_genre_cache: dict[str, dict[int, str]] = {}


class TmdbError(HTTPException):
    def __init__(self, detail: str, status_code: int = 424):
        super().__init__(status_code=status_code, detail=detail)


def get_api_key(db: Session) -> str:
    row = db.get(AppSettings, 1)
    if row and row.tmdb_api_key:
        return row.tmdb_api_key

    from app.config import get_settings

    env_key = get_settings().tmdb_api_key
    if env_key:
        return env_key

    raise TmdbError(
        "No TMDb API key configured. Add one on the Settings page — "
        "get a free key at https://www.themoviedb.org/settings/api"
    )


def _client() -> httpx.Client:
    return httpx.Client(base_url=TMDB_BASE, timeout=10.0)


def _get(db: Session, path: str, params: dict | None = None) -> dict:
    api_key = get_api_key(db)
    params = {**(params or {}), "api_key": api_key}
    try:
        with _client() as client:
            resp = client.get(path, params=params)
    except httpx.RequestError as exc:
        raise TmdbError(f"Could not reach TMDb: {exc}") from exc

    if resp.status_code == 401:
        raise TmdbError("TMDb rejected the API key — check it on the Settings page.", 401)
    if resp.status_code == 404:
        raise TmdbError("Not found on TMDb.", 404)
    if resp.status_code >= 400:
        raise TmdbError(f"TMDb returned {resp.status_code}.", 502)

    return resp.json()


def genre_map(db: Session, media_type: str) -> dict[int, str]:
    """Cached id -> name map, e.g. {28: 'Action'}."""
    if media_type in _genre_cache:
        return _genre_cache[media_type]

    kind = "movie" if media_type == "movie" else "tv"
    data = _get(db, f"/genre/{kind}/list")
    mapping = {g["id"]: g["name"] for g in data.get("genres", [])}
    _genre_cache[media_type] = mapping
    return mapping


def _poster(path: str | None) -> str | None:
    return f"{IMAGE_BASE}{path}" if path else None


def _normalize_media_type(tmdb_media_type: str) -> str:
    return "series" if tmdb_media_type == "tv" else "movie"


# TMDb's genre taxonomy is stable and shared across movie/tv: 99 =
# Documentary, 16 = Animation. Both are excluded from Recommendations and
# Browse entirely — Animation is excluded unconditionally now (not just
# anime), since Western animation was still slipping through: TMDb tags a
# lot of family/kids content with both "Animation" and whatever content
# genre it also has (e.g. Action & Adventure), so an Animation title could
# still surface under an unrelated genre filter.
_DOCUMENTARY_GENRE_ID = 99
_ANIMATION_GENRE_ID = 16


def _is_documentary_or_animation(genre_ids: list[int]) -> bool:
    return _DOCUMENTARY_GENRE_ID in genre_ids or _ANIMATION_GENRE_ID in genre_ids


def search_multi(
    db: Session,
    query: str,
    limit: int = 10,
    exclude_documentaries_and_animation: bool = False,
) -> list[dict]:
    data = _get(db, "/search/multi", {"query": query, "include_adult": "false"})
    results = []
    for item in data.get("results", []):
        media_type = item.get("media_type")
        if media_type not in ("movie", "tv"):
            continue
        if exclude_documentaries_and_animation and _is_documentary_or_animation(
            item.get("genre_ids", [])
        ):
            continue
        title = item.get("title") or item.get("name")
        date_str = item.get("release_date") or item.get("first_air_date") or ""
        year = int(date_str[:4]) if date_str[:4].isdigit() else None
        results.append(
            {
                "tmdb_id": item["id"],
                "title": title,
                "media_type": _normalize_media_type(media_type),
                "year": year,
                "poster_path": _poster(item.get("poster_path")),
                "imdb_rating": round(item.get("vote_average") or 0, 1),
            }
        )
        if len(results) >= limit:
            break
    return results


def top_rated(db: Session, media_type: str, page: int = 1) -> list[dict]:
    kind = "movie" if media_type == "movie" else "tv"
    genres = genre_map(db, media_type)
    data = _get(db, f"/{kind}/top_rated", {"page": page})

    results = []
    for item in data.get("results", []):
        genre_ids = item.get("genre_ids", [])
        if _is_documentary_or_animation(genre_ids):
            continue
        title = item.get("title") or item.get("name")
        date_str = item.get("release_date") or item.get("first_air_date") or ""
        year = int(date_str[:4]) if date_str[:4].isdigit() else 0
        genre_names = [genres.get(gid, "") for gid in genre_ids]
        genre_names = [g for g in genre_names if g][:3]
        results.append(
            {
                "tmdb_id": item["id"],
                "title": title,
                "media_type": media_type,
                "year": year,
                "poster_path": _poster(item.get("poster_path")),
                "imdb_rating": round(item.get("vote_average") or 0, 1),
                "genres": genre_names,
            }
        )
    return results


def popular(db: Session, media_type: str, page: int = 1) -> list[dict]:
    """TMDb's `/popular` endpoint — mainstream, widely-watched titles.
    Used for the Browse page, distinct from `top_rated` (which skews toward
    critically acclaimed/niche titles) since the point here is surfacing
    things a typical viewer has actually seen."""
    kind = "movie" if media_type == "movie" else "tv"
    data = _get(db, f"/{kind}/popular", {"page": page})

    results = []
    for item in data.get("results", []):
        if _is_documentary_or_animation(item.get("genre_ids", [])):
            continue
        title = item.get("title") or item.get("name")
        date_str = item.get("release_date") or item.get("first_air_date") or ""
        year = int(date_str[:4]) if date_str[:4].isdigit() else 0
        results.append(
            {
                "tmdb_id": item["id"],
                "title": title,
                "media_type": media_type,
                "year": year,
                "poster_path": _poster(item.get("poster_path")),
                "imdb_rating": round(item.get("vote_average") or 0, 1),
            }
        )
    return results


def discover(
    db: Session,
    media_type: str,
    genre_ids: list[int],
    exclude_ids: set[int],
    min_rating: float = 0.0,
    min_year: int | None = None,
    origin_country: str | None = None,
    limit: int = 12,
    max_pages: int = 5,
) -> list[dict]:
    kind = "movie" if media_type == "movie" else "tv"
    genres = genre_map(db, media_type)
    base_params = {
        "sort_by": "vote_average.desc",
        "vote_count.gte": 300,
        "vote_average.gte": max(min_rating, 6.0),
    }
    if genre_ids:
        # Pipe-separated = OR in TMDb's query syntax ("any of these genres").
        # Comma-separated would mean AND ("all of these genres at once"),
        # which is far too restrictive for a "matches your top genres" or
        # "matches any selected genre" filter — it was quietly starving
        # recommendations down to a handful of results.
        base_params["with_genres"] = "|".join(str(g) for g in genre_ids)
    if min_year:
        # "This year through present" — TMDb's top_rated endpoint has no
        # date filter at all, which is why a year filter forces the
        # /discover path regardless of watch history.
        date_field = "primary_release_date.gte" if kind == "movie" else "first_air_date.gte"
        base_params[date_field] = f"{min_year}-01-01"
    if origin_country:
        # with_origin_country is an undocumented-but-confirmed-stable TMDb
        # discover filter (single ISO 3166-1 country code per call). Its
        # multi-value OR syntax isn't documented, so multi-country
        # selection is handled by the caller issuing one call per country
        # and merging results, rather than trusting an unverified pipe
        # join here.
        base_params["with_origin_country"] = origin_country

    results = []
    for page in range(1, max_pages + 1):
        data = _get(db, f"/discover/{kind}", {**base_params, "page": page})
        page_results = data.get("results", [])
        if not page_results:
            break

        for item in page_results:
            if item["id"] in exclude_ids:
                continue
            item_genre_ids = item.get("genre_ids", [])
            if _is_documentary_or_animation(item_genre_ids):
                continue
            title = item.get("title") or item.get("name")
            date_str = item.get("release_date") or item.get("first_air_date") or ""
            year = int(date_str[:4]) if date_str[:4].isdigit() else 0
            genre_names = [genres.get(gid, "") for gid in item_genre_ids]
            genre_names = [g for g in genre_names if g][:3]
            results.append(
                {
                    "tmdb_id": item["id"],
                    "title": title,
                    "media_type": media_type,
                    "year": year,
                    "poster_path": _poster(item.get("poster_path")),
                    "imdb_rating": round(item.get("vote_average") or 0, 1),
                    "genres": genre_names,
                }
            )
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return results[:limit]


def get_details(db: Session, media_type: str, tmdb_id: int) -> dict:
    """Full details + credits, used when marking a title watched/queued so we
    can store runtime, director/creator, top cast, and genres directly."""
    kind = "movie" if media_type == "movie" else "tv"
    data = _get(db, f"/{kind}/{tmdb_id}", {"append_to_response": "credits"})

    if kind == "movie":
        runtime = data.get("runtime") or 0
        director = next(
            (c["name"] for c in data.get("credits", {}).get("crew", []) if c.get("job") == "Director"),
            None,
        )
        year_str = (data.get("release_date") or "")[:4]
    else:
        episode_run = data.get("episode_run_time") or [45]
        runtime = episode_run[0] if episode_run else 45
        creators = data.get("created_by") or []
        director = creators[0]["name"] if creators else None
        year_str = (data.get("first_air_date") or "")[:4]

    cast = [c["name"] for c in data.get("credits", {}).get("cast", [])[:3]]

    return {
        "tmdb_id": tmdb_id,
        "title": data.get("title") or data.get("name"),
        "media_type": _normalize_media_type(kind),
        "year": int(year_str) if year_str.isdigit() else 0,
        "genres": [g["name"] for g in data.get("genres", [])][:3],
        "imdb_rating": round(data.get("vote_average") or 0, 1),
        "runtime_minutes": runtime,
        "poster_path": _poster(data.get("poster_path")),
        "director": director,
        "cast": cast,
        "number_of_seasons": data.get("number_of_seasons"),
        "status": data.get("status"),
        "next_episode_to_air": data.get("next_episode_to_air"),
        "last_air_date": data.get("last_air_date"),
        # Per-season air dates — used to determine whether a season aired
        # before or after the user's watched_date, rather than just
        # comparing season counts (which breaks the moment someone marks a
        # multi-season show watched, since watched-season-count and
        # available-season-count are different things).
        "seasons": [
            {"season_number": s.get("season_number"), "air_date": s.get("air_date")}
            for s in data.get("seasons", [])
        ],
    }
