from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class CanvasSettings(BaseSettings):
    base_url: str
    access_token: SecretStr

    model_config = SettingsConfigDict(
        env_prefix="CANVAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )