# Entertainment OS — API

FastAPI + SQLAlchemy + SQLite backend for Entertainment OS. Serves watched
history, watchlist, recommendations, analytics, and season notifications,
all backed by TMDb.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

API docs (interactive): `http://localhost:8000/docs`

## TMDb key

Get a free key at https://www.themoviedb.org/settings/api (the "API Read
Access Token" isn't needed — use the v3 API key).

You can set it two ways:
- **Recommended**: paste it into the app's Settings page once the frontend
  is running — it's stored in the database and used for every request.
- **Local dev shortcut**: set `TMDB_API_KEY` in `.env`. This is only a
  fallback — a key saved via Settings always takes priority.

Until a key is set, `/api/recommendations`, `/api/search`, and
`/api/notifications` return a clear `424` error rather than failing
silently. Everything else (`/api/watched`, `/api/watchlist`,
`/api/analytics`, `/api/settings`, `/api/activity`) works with zero
external dependencies.

## Data note

TMDb's free API doesn't expose IMDb's actual rating — that requires OMDb, a
separate service, which is out of scope here. Ratings shown throughout the
app are TMDb's own community `vote_average` (same 0–10 scale), kept in a
field called `imdb_rating` for continuity with the frontend. If you want
true IMDb ratings, swap `app/services/tmdb.py` for a service that queries
OMDb by title/year.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/api/watched` | List / log a watched title |
| PATCH/DELETE | `/api/watched/{id}` | Toggle favorite / remove |
| GET/POST | `/api/watchlist` | List / queue a title |
| DELETE | `/api/watchlist/{id}` | Remove from queue |
| POST | `/api/watchlist/{id}/mark-watched` | Move into Watched |
| GET | `/api/recommendations` | Cold-start or genre-based suggestions |
| POST | `/api/recommendations/{tmdb_id}/ignore` | Dismiss permanently |
| POST | `/api/recommendations/{tmdb_id}/watchlist` | Queue a suggestion |
| POST | `/api/recommendations/{tmdb_id}/watched` | Log a suggestion as watched |
| GET | `/api/analytics` | Genre/year distributions, top genres/directors/actors |
| GET | `/api/notifications` | New/upcoming seasons for watched series |
| GET/PUT | `/api/settings` | TMDb key + recommendation preferences |
| GET | `/api/search?q=` | TMDb title search (autocomplete) |
| GET | `/api/search/details/{media_type}/{tmdb_id}` | Full TMDb detail lookup |
| GET | `/api/activity` | Recent activity feed |

## Database

SQLite by default (`entertainment_os.db`, created automatically on first
run). To move to Postgres (e.g. Render's managed Postgres), set
`DATABASE_URL` in `.env` — no code changes needed, SQLAlchemy handles both.

Tables are created directly via `Base.metadata.create_all()` — fine for
this project's size. If the schema needs to evolve later without losing
data, introduce Alembic migrations at that point.
