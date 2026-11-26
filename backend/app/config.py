from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "trainer"
    environment: str = "local"
    api_prefix: str = "/v1"

    database_url: str = "postgresql://trainer:trainer@localhost:5434/trainer"
    # Solo/dev: skip JWT and trust this user id when X-User-Id header is sent.
    dev_user_id: str = "00000000-0000-4000-8000-000000000001"
    allow_dev_auth: bool = True

    gemini_api_key: str = ""
    gemini_flash_model: str = "gemini-3.1-flash-lite"
    gemini_frontier_model: str = "gemini-3.5-flash"
    gemini_embed_model: str = "gemini-embedding-001"
    embedding_dims: int = 768
    embedding_output_dims: int = 768

    job_secret: str = "local-job-secret-change-me"
    cors_origins: str = "*"

    default_timezone: str = "Asia/Kolkata"
    default_weight_kg: float = 70.0
    default_height_cm: float = 175.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
