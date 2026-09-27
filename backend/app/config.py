"""Application configuration, loaded from environment variables / backend/.env.

Why pydantic-settings: it validates types at startup and fails loudly with a
clear message when a required var is missing, instead of surfacing a cryptic
None deep inside a DB call. The SQLite default lets the app boot for local
smoke tests before a real Postgres URL exists; in production (.env or Render
env vars) DATABASE_URL always points at Supabase Postgres.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",          # backend/.env when run from backend/
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./local_dev.db"
    openweather_api_key: str = ""


settings = Settings()
