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


def search_multi(db: Session, query: str, limit: int = 10) -> list[dict]:
    data = _get(db, "/search/multi", {"query": query, "include_adult": "false"})
    results = []
    for item in data.get("results", []):
        media_type = item.get("media_type")
        if media_type not in ("movie", "tv"):
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
        title = item.get("title") or item.get("name")
        date_str = item.get("release_date") or item.get("first_air_date") or ""
        year = int(date_str[:4]) if date_str[:4].isdigit() else 0
        genre_names = [genres.get(gid, "") for gid in item.get("genre_ids", [])]
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


def discover(
    db: Session,
    media_type: str,
    genre_ids: list[int],
    exclude_ids: set[int],
    min_rating: float = 0.0,
    limit: int = 12,
) -> list[dict]:
    kind = "movie" if media_type == "movie" else "tv"
    genres = genre_map(db, media_type)
    params = {
        "sort_by": "vote_average.desc",
        "vote_count.gte": 300,
        "vote_average.gte": max(min_rating, 6.0),
    }
    if genre_ids:
        params["with_genres"] = ",".join(str(g) for g in genre_ids)

    data = _get(db, f"/discover/{kind}", params)
    results = []
    for item in data.get("results", []):
        if item["id"] in exclude_ids:
            continue
        title = item.get("title") or item.get("name")
        date_str = item.get("release_date") or item.get("first_air_date") or ""
        year = int(date_str[:4]) if date_str[:4].isdigit() else 0
        genre_names = [genres.get(gid, "") for gid in item.get("genre_ids", [])]
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
    return results


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
    }
