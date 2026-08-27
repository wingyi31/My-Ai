from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    app_name: str = "StudyOps Ingestion API"
    app_env: str = "local"

    mytimes_base_url: str = (
        "https://mytimes.taylors.edu.my"
    )
    mytimes_token: SecretStr | None = None
    moodle_request_timeout_seconds: float = 30.0
    http_trust_env: bool = False

    # Canvas is intentionally exposed through
    # GET-only application routes.
    canvas_base_url: str = (
        "https://canvas.nus.edu.sg"
    )
    canvas_access_token: SecretStr | None = None
    canvas_request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
    )
    canvas_sync_lease_seconds: int = Field(
        default=1800,
        ge=60,
        le=7200,
    )

    # Google Cloud, Firestore and RAG settings.
    google_cloud_project: str = Field(
        min_length=1,
    )
    google_cloud_location: str = "global"
    firestore_database: str = "(default)"

    embedding_model: str = (
        "gemini-embedding-001"
    )
    embedding_dimension: int = Field(
        default=768,
        ge=1,
        le=2048,
    )

    generation_model: str = (
        "gemini-3.7-flash"
    )
    rag_default_source_limit: int = Field(
        default=8,
        ge=1,
        le=20,
    )
    rag_min_similarity: float = Field(
    default=0.60,
    ge=0.0,
    le=1.0,
    )

    cloud_tasks_location: str = (
        "asia-southeast1"
    )
    cloud_tasks_queue: str = (
        "canvas-sync"
    )
    cloud_tasks_worker_base_url: (
        str | None
    ) = None
    cloud_tasks_service_account_email: (
        str | None
    ) = None
    cloud_tasks_dispatch_deadline_seconds: int = Field(
        default=1800,
        ge=60,
        le=1800,
    )

    # Google OAuth credentials for a Web
    # application. Gmail access is read-only.
    gmail_client_id: SecretStr | None = None
    gmail_client_secret: SecretStr | None = None
    gmail_redirect_uri: str = (
        "http://localhost:8000/"
        "gmail/oauth/callback"
    )
    gmail_oauth_state_secret: (
        SecretStr | None
    ) = None
    gmail_refresh_token: SecretStr | None = None
    gmail_token_path: Path = Path(
        "data/gmail_credentials.json"
    )
    gmail_sync_state_path: Path = Path(
        "data/gmail_sync_state.json"
    )
    gmail_sync_query: str = "in:inbox"
    gmail_max_messages_per_sync: int = Field(
        default=50,
        ge=1,
        le=500,
    )
    gmail_request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
    )

    # Set this for local testing. In production,
    # prefer private Cloud Run + IAM.
    scheduler_shared_secret: (
        SecretStr | None
    ) = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()