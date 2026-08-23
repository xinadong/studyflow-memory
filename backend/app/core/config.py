"""Application settings and environment configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_URL = f"sqlite:///{(PROJECT_ROOT / 'data' / 'studyflow.db').as_posix()}"


class Settings(BaseSettings):
    app_name: str = "StudyFlow Memory API"
    database_url: str = DEFAULT_DATABASE_URL
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "gpt-5.6-terra"
    llm_max_retries: int = 2
    request_timeout_seconds: float = 20.0
    # Resolve the shared project .env independently of the process cwd.
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
