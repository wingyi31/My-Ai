from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.routes import router
from app.connectors.canvas import CanvasClient
from app.connectors.gmail.client import GmailClient
from app.connectors.gmail.oauth import (
    GmailCredentialStore,
    GmailOAuthClient,
    OAuthStateSigner,
)
from app.connectors.gmail.service import GmailService
from app.connectors.moodle import MoodleClient
from app.core.config import get_settings
from app.jobs.gmail_sync import GmailSyncJob, JsonGmailSyncStateStore
from app.routes.canvas import router as canvas_router
from app.routes.gmail import router as gmail_router
from app.workers.email_processor import EmailProcessor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create one pooled HTTP client for the lifetime of the Cloud Run instance."""
    settings = get_settings()
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.moodle_request_timeout_seconds),
        follow_redirects=False,
        trust_env=settings.http_trust_env,
    )
    gmail_http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.gmail_request_timeout_seconds),
        follow_redirects=False,
        trust_env=settings.http_trust_env,
    )
    canvas_http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.canvas_request_timeout_seconds),
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
    app.state.canvas_client = CanvasClient(
        http_client=canvas_http_client,
        base_url=settings.canvas_base_url,
        access_key=(
            settings.canvas_access_key.get_secret_value()
            if settings.canvas_access_key
            else None
        ),
    )
    gmail_credential_store = GmailCredentialStore(
        configured_refresh_token=(
            settings.gmail_refresh_token.get_secret_value()
            if settings.gmail_refresh_token
            else None
        ),
        path=settings.gmail_token_path,
    )
    gmail_oauth_client = GmailOAuthClient(
        http_client=gmail_http_client,
        client_id=(
            settings.gmail_client_id.get_secret_value()
            if settings.gmail_client_id
            else None
        ),
        client_secret=(
            settings.gmail_client_secret.get_secret_value()
            if settings.gmail_client_secret
            else None
        ),
        redirect_uri=settings.gmail_redirect_uri,
        state_signer=OAuthStateSigner(
            settings.gmail_oauth_state_secret.get_secret_value()
            if settings.gmail_oauth_state_secret
            else None
        ),
    )
    gmail_client = GmailClient(
        http_client=gmail_http_client,
        oauth_client=gmail_oauth_client,
        credential_store=gmail_credential_store,
    )
    gmail_service = GmailService(gmail_client, EmailProcessor())
    app.state.gmail_credential_store = gmail_credential_store
    app.state.gmail_oauth_client = gmail_oauth_client
    app.state.gmail_client = gmail_client
    app.state.gmail_sync_job = GmailSyncJob(
        service=gmail_service,
        state_store=JsonGmailSyncStateStore(settings.gmail_sync_state_path),
        query=settings.gmail_sync_query,
        max_messages=settings.gmail_max_messages_per_sync,
    )
    try:
        yield
    finally:
        await http_client.aclose()
        await gmail_http_client.aclose()
        await canvas_http_client.aclose()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(canvas_router)
app.include_router(gmail_router)
