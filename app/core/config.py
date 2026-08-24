from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "StudyOps Ingestion API"
    app_env: str = "local"

    mytimes_base_url: str = "https://mytimes.taylors.edu.my"
    mytimes_token: SecretStr | None = None
    moodle_request_timeout_seconds: float = 30.0
    http_trust_env: bool = False

    # Google OAuth credentials for a Web application. Gmail access is read-only.
    gmail_client_id: SecretStr | None = None
    gmail_client_secret: SecretStr | None = None
    gmail_redirect_uri: str = "http://localhost:8000/gmail/oauth/callback"
    gmail_oauth_state_secret: SecretStr | None = None
    gmail_refresh_token: SecretStr | None = None
    gmail_token_path: Path = Path("data/gmail_credentials.json")
    gmail_sync_state_path: Path = Path("data/gmail_sync_state.json")
    gmail_sync_query: str = "in:inbox"
    gmail_max_messages_per_sync: int = Field(default=50, ge=1, le=500)
    gmail_request_timeout_seconds: float = Field(default=30.0, gt=0)

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
