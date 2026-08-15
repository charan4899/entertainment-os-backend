from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WatchedItem
from app.schemas import NotificationOut
from app.services import tmdb
from app.services.tmdb import TmdbError

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@router.get("", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db)):
    candidates = (
        db.query(WatchedItem)
        .filter(WatchedItem.media_type == "series", WatchedItem.tmdb_id.isnot(None))
        .all()
    )
    if not candidates:
        return []

    today = datetime.now().date()
    notifications: list[NotificationOut] = []

    for item in candidates:
        try:
            details = tmdb.get_details(db, "series", item.tmdb_id)
        except TmdbError:
            # Skip titles TMDb can't resolve (or if no key is configured yet)
            # rather than failing the whole notifications list.
            continue

        watched_date = item.watched_date

        # A season only counts as "new" if it aired strictly after the date
        # you marked this show watched — comparing season *counts* breaks
        # the moment a multi-season show gets marked watched all at once,
        # since "seasons watched" and "seasons that exist" both land on the
        # same number and every prior season looks unwatched.
        newly_aired = [
            s
            for s in details.get("seasons", [])
            if (s.get("season_number") or 0) > 0
            and (air_date := _parse_date(s.get("air_date")))
            and watched_date < air_date <= today
        ]

        if newly_aired:
            latest = max(newly_aired, key=lambda s: s["season_number"])
            air_date = _parse_date(latest["air_date"])
            notifications.append(
                NotificationOut(
                    series_title=item.title,
                    tmdb_id=item.tmdb_id,
                    kind="season_released",
                    message=(
                        f"Season {latest['season_number']} released "
                        f"{air_date.isoformat()} — after you marked this watched."
                    ),
                    season_number=latest["season_number"],
                )
            )
            continue

        next_episode = details.get("next_episode_to_air") or {}
        next_air_date = _parse_date(next_episode.get("air_date"))
        if next_air_date and next_air_date > today and next_air_date > watched_date:
            notifications.append(
                NotificationOut(
                    series_title=item.title,
                    tmdb_id=item.tmdb_id,
                    kind="season_announced",
                    message=(
                        f"Season {next_episode.get('season_number')} of {item.title} "
                        f"is scheduled for {next_air_date.isoformat()}."
                    ),
                    season_number=next_episode.get("season_number"),
                )
            )
        elif details.get("status") == "In Production":
            notifications.append(
                NotificationOut(
                    series_title=item.title,
                    tmdb_id=item.tmdb_id,
                    kind="season_announced",
                    message=f"A new season of {item.title} is in production.",
                    season_number=(details.get("number_of_seasons") or 0) + 1,
                )
            )

    return notifications
