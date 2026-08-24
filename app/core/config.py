from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "StudyOps Ingestion API"
    app_env: str = "local"

    mytimes_base_url: str = "https://mytimes.taylors.edu.my"
    mytimes_token: SecretStr | None = None
    moodle_request_timeout_seconds: float = 30.0
    http_trust_env: bool = False

    # Set this for local testing. In production, prefer private Cloud Run + IAM.
    scheduler_shared_secret: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
