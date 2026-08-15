from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WatchedItem
from app.schemas import NotificationOut
from app.services import tmdb
from app.services.tmdb import TmdbError

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db)):
    candidates = (
        db.query(WatchedItem)
        .filter(WatchedItem.media_type == "series", WatchedItem.tmdb_id.isnot(None))
        .all()
    )
    if not candidates:
        return []

    notifications: list[NotificationOut] = []

    for item in candidates:
        try:
            details = tmdb.get_details(db, "series", item.tmdb_id)
        except TmdbError:
            # Skip titles TMDb can't resolve (or if no key is configured yet)
            # rather than failing the whole notifications list.
            continue

        watched_seasons = item.seasons_watched or 0
        available_seasons = details.get("number_of_seasons") or 0

        if available_seasons > watched_seasons:
            notifications.append(
                NotificationOut(
                    series_title=item.title,
                    tmdb_id=item.tmdb_id,
                    kind="season_released",
                    message=f"Season {available_seasons} is out — you've logged through season {watched_seasons}.",
                    season_number=available_seasons,
                )
            )
        elif details.get("status") == "In Production":
            notifications.append(
                NotificationOut(
                    series_title=item.title,
                    tmdb_id=item.tmdb_id,
                    kind="season_announced",
                    message=f"A new season of {item.title} is in production.",
                    season_number=available_seasons + 1,
                )
            )

    return notifications
