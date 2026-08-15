import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WatchedItem(Base):
    __tablename__ = "watched_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)  # "movie" | "series"
    imdb_rating: Mapped[float] = mapped_column(Float, default=0.0)
    genres: Mapped[list[str]] = mapped_column(JSON, default=list)
    year: Mapped[int] = mapped_column(Integer, default=0)
    watched_date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date())
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    runtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    seasons_watched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String, nullable=True)
    director: Mapped[str | None] = mapped_column(String, nullable=True)
    cast: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    imdb_rating: Mapped[float] = mapped_column(Float, default=0.0)
    genres: Mapped[list[str]] = mapped_column(JSON, default=list)
    year: Mapped[int] = mapped_column(Integer, default=0)
    added_date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date())
    runtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    poster_path: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[str] = mapped_column(String, default="medium")  # low | medium | high
    director: Mapped[str | None] = mapped_column(String, nullable=True)
    cast: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class IgnoredRecommendation(Base):
    """Titles the user dismissed — excluded from future recommendation batches."""

    __tablename__ = "ignored_recommendations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    ignored_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    label: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # watched | watchlist | favorite | system
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AppSettings(Base):
    """Singleton row (id is always 1) holding app-wide configuration."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    tmdb_api_key: Mapped[str | None] = mapped_column(String, nullable=True)
    include_movies: Mapped[bool] = mapped_column(Boolean, default=True)
    include_series: Mapped[bool] = mapped_column(Boolean, default=True)
    min_recommendation_rating: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
