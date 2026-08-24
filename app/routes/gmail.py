from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from app.api.routes import verify_scheduler_secret
from app.connectors.gmail.client import GmailApiError
from app.connectors.gmail.oauth import (
    GmailNotConfiguredError,
    GmailOAuthError,
    InvalidOAuthStateError,
)
from app.connectors.gmail.service import GmailMessageProcessingError
from app.jobs.gmail_sync import GmailSyncStateError

router = APIRouter(tags=["gmail"])


@router.get(
    "/gmail/status",
    summary="Show non-sensitive Gmail connection status",
)
async def gmail_status(request: Request) -> dict[str, bool]:
    try:
        connected = request.app.state.gmail_credential_store.has_refresh_token()
    except GmailOAuthError:
        connected = False
    return {
        "oauth_configured": request.app.state.gmail_oauth_client.is_configured,
        "connected": connected,
    }


@router.get(
    "/gmail/oauth/authorize",
    summary="Start Google's read-only Gmail OAuth flow",
)
async def gmail_oauth_authorize(request: Request) -> RedirectResponse:
    try:
        url = request.app.state.gmail_oauth_client.authorization_url()
    except GmailNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get(
    "/gmail/oauth/callback",
    summary="Complete Google's read-only Gmail OAuth flow",
)
async def gmail_oauth_callback(
    request: Request,
    code: Annotated[str | None, Query()] = None,
    state_value: Annotated[str | None, Query(alias="state")] = None,
    error: Annotated[str | None, Query()] = None,
) -> dict[str, str | bool]:
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authorization was not completed: {error}",
        )
    if not code or not state_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback requires code and state",
        )

    try:
        tokens = await request.app.state.gmail_oauth_client.exchange_code(
            code=code,
            state=state_value,
        )
        credential_store = request.app.state.gmail_credential_store
        refresh_token_saved = tokens.refresh_token is not None
        if tokens.refresh_token:
            credential_store.save_refresh_token(tokens.refresh_token)
        elif not credential_store.has_refresh_token():
            raise GmailOAuthError(
                "Google returned no refresh token. Revoke the app grant and authorize "
                "again so Google can issue one."
            )
        request.app.state.gmail_client.invalidate_access_token()
    except InvalidOAuthStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except GmailNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except GmailOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return {
        "status": "connected",
        "scope": tokens.scope or "gmail.readonly",
        "refresh_token_saved": refresh_token_saved,
    }


@router.post(
    "/internal/scheduler/gmail",
    summary="Run one Gmail bootstrap or incremental synchronization",
)
async def run_gmail_sync(
    request: Request,
    x_scheduler_secret: Annotated[str | None, Header()] = None,
) -> dict:
    verify_scheduler_secret(x_scheduler_secret)
    try:
        return await request.app.state.gmail_sync_job.run()
    except GmailNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (GmailApiError, GmailOAuthError, GmailMessageProcessingError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except GmailSyncStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
