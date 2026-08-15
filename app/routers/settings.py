from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppSettings
from app.schemas import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _get_or_create(db: Session) -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _to_out(row: AppSettings) -> SettingsOut:
    return SettingsOut(
        tmdb_api_key_set=bool(row.tmdb_api_key),
        include_movies=row.include_movies,
        include_series=row.include_series,
        min_recommendation_rating=row.min_recommendation_rating,
    )


@router.get("", response_model=SettingsOut)
def get_settings_route(db: Session = Depends(get_db)):
    return _to_out(_get_or_create(db))


@router.put("", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    row = _get_or_create(db)
    data = payload.model_dump(exclude_unset=True)

    # An empty string clears the key; omitting the field leaves it untouched.
    if "tmdb_api_key" in data and data["tmdb_api_key"] == "":
        data["tmdb_api_key"] = None

    for field, value in data.items():
        setattr(row, field, value)

    db.commit()
    db.refresh(row)
    return _to_out(row)
