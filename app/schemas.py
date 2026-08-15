from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MediaType = Literal["movie", "series"]
Priority = Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Watched
# ---------------------------------------------------------------------------

class WatchedBase(BaseModel):
    tmdb_id: int | None = None
    title: str
    media_type: MediaType
    imdb_rating: float = 0.0
    genres: list[str] = Field(default_factory=list)
    year: int = 0
    watched_date: date | None = None
    favorite: bool = False
    runtime_minutes: int = 0
    seasons_watched: int | None = None
    poster_path: str | None = None
    director: str | None = None
    cast: list[str] = Field(default_factory=list)


class WatchedCreate(WatchedBase):
    pass


class WatchedUpdate(BaseModel):
    favorite: bool | None = None
    seasons_watched: int | None = None


class WatchedOut(WatchedBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    watched_date: date


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

class WatchlistBase(BaseModel):
    tmdb_id: int | None = None
    title: str
    media_type: MediaType
    imdb_rating: float = 0.0
    genres: list[str] = Field(default_factory=list)
    year: int = 0
    runtime_minutes: int = 0
    poster_path: str | None = None
    priority: Priority = "medium"
    director: str | None = None
    cast: list[str] = Field(default_factory=list)


class WatchlistCreate(WatchlistBase):
    pass


class WatchlistOut(WatchlistBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    added_date: date


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

class RecommendationOut(BaseModel):
    tmdb_id: int
    title: str
    media_type: MediaType
    imdb_rating: float
    genres: list[str]
    year: int
    reason: str
    match_score: int
    poster_path: str | None = None


class RecommendationAction(BaseModel):
    tmdb_id: int
    media_type: MediaType


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    label: str
    detail: str
    kind: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class SettingsOut(BaseModel):
    tmdb_api_key_set: bool
    include_movies: bool
    include_series: bool
    min_recommendation_rating: float


class SettingsUpdate(BaseModel):
    tmdb_api_key: str | None = None
    include_movies: bool | None = None
    include_series: bool | None = None
    min_recommendation_rating: float | None = None


# ---------------------------------------------------------------------------
# Search (TMDb passthrough, used by the Add-to-watchlist dialog)
# ---------------------------------------------------------------------------

class SearchResultOut(BaseModel):
    tmdb_id: int
    title: str
    media_type: MediaType
    year: int | None = None
    poster_path: str | None = None
    imdb_rating: float = 0.0


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class GenreCount(BaseModel):
    genre: str
    count: int


class YearCount(BaseModel):
    year: int
    count: int


class NameCount(BaseModel):
    name: str
    count: int


class AnalyticsOut(BaseModel):
    movies_watched: int
    series_watched: int
    total_watch_minutes: int
    genre_distribution: list[GenreCount]
    release_year_distribution: list[YearCount]
    top_genres: list[GenreCount]
    top_directors: list[NameCount]
    top_actors: list[NameCount]


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class NotificationOut(BaseModel):
    series_title: str
    tmdb_id: int
    kind: Literal["season_released", "season_announced"]
    message: str
    season_number: int | None = None


# ---------------------------------------------------------------------------
# Browse (popular titles + search, for bulk "mark what I've already watched")
# ---------------------------------------------------------------------------

class BrowseResultOut(BaseModel):
    tmdb_id: int
    title: str
    media_type: MediaType
    year: int | None = None
    poster_path: str | None = None
    imdb_rating: float = 0.0
    already_watched: bool = False
    in_watchlist: bool = False


# ---------------------------------------------------------------------------
# One-off maintenance: backfill seasons_watched for rows written before the
# "mark watched" endpoints were fixed to record the real season count.
# ---------------------------------------------------------------------------

class BackfillSeasonsItem(BaseModel):
    title: str
    previous_seasons_watched: int | None
    new_seasons_watched: int


class BackfillSeasonsResult(BaseModel):
    updated: list[BackfillSeasonsItem]
    unchanged_count: int
    skipped_count: int
