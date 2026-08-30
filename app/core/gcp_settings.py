from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class GcpSettings(BaseSettings):
    project_id: str

    model_config = SettingsConfigDict(
        env_prefix="GCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )