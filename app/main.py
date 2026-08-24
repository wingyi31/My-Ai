from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.routes import router
from app.connectors.moodle import MoodleClient
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create one pooled HTTP client for the lifetime of the Cloud Run instance."""
    settings = get_settings()
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.moodle_request_timeout_seconds),
        follow_redirects=False,
        trust_env=settings.http_trust_env,
    )
    app.state.moodle_client = MoodleClient(
        http_client=http_client,
        base_url=settings.mytimes_base_url,
        token=settings.mytimes_token.get_secret_value()
        if settings.mytimes_token
        else None,
    )
    try:
        yield
    finally:
        await http_client.aclose()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
