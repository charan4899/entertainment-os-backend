from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers import activity, analytics, browse, notifications, recommendations, search, settings, watched, watchlist

settings_obj = get_settings()

# SQLite MVP: create tables directly. Swap for Alembic migrations once the
# schema needs to evolve without dropping data (e.g. after moving to Postgres).
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Entertainment OS API",
    description="Backend for Entertainment OS — watched history, watchlist, "
    "recommendations, analytics, and season notifications, backed by TMDb.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_obj.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(watched.router)
app.include_router(watchlist.router)
app.include_router(recommendations.router)
app.include_router(analytics.router)
app.include_router(notifications.router)
app.include_router(settings.router)
app.include_router(search.router)
app.include_router(activity.router)
app.include_router(browse.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
