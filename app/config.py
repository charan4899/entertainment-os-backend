from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Runtime configuration, loaded from environment variables (or a local
    .env file in development). None of these have secrets baked in —
    the TMDb key in particular is expected to be set via the Settings
    page in the app (stored in the DB) or as an env var fallback for
    local development.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite by default — swap DATABASE_URL for Postgres in production
    # (e.g. Render's managed Postgres) without touching any router code.
    database_url: str = "sqlite:///./entertainment_os.db"

    # Comma-separated list of origins allowed to call this API.
    # Set this to your deployed Vercel URL(s) in production.
    cors_origins: str = "http://localhost:3000"

    # Optional fallback TMDb key for local dev — the Settings page writes
    # its own key into the database, which always takes priority.
    tmdb_api_key: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
