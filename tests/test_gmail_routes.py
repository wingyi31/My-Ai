from fastapi.testclient import TestClient

from app.connectors.gmail.oauth import (
    GmailNotConfiguredError,
)
from app.core.config import get_settings
from app.main import app


class DisconnectedCredentialStore:

    def has_refresh_token(self) -> bool:
        return False


class UnconfiguredOAuthClient:

    @property
    def is_configured(self) -> bool:
        return False


class MissingConnectionSyncJob:

    async def run(self) -> dict:
        raise GmailNotConfiguredError(
            "Gmail is not connected"
        )


def scheduler_headers() -> dict[str, str]:
    configured_secret = (
        get_settings()
        .scheduler_shared_secret
    )

    if configured_secret is None:
        return {}

    return {
        "X-Scheduler-Secret": (
            configured_secret
            .get_secret_value()
        )
    }


def test_gmail_status_does_not_expose_secrets() -> None:
    with TestClient(app) as client:
        app.state.gmail_credential_store = (
            DisconnectedCredentialStore()
        )
        app.state.gmail_oauth_client = (
            UnconfiguredOAuthClient()
        )

        response = client.get(
            "/gmail/status"
        )

    assert response.status_code == 200
    assert response.json() == {
        "oauth_configured": False,
        "connected": False,
    }

    response_text = response.text.casefold()

    assert "client_secret" not in response_text
    assert "refresh_token" not in response_text


def test_gmail_sync_explains_missing_connection() -> None:
    with TestClient(app) as client:
        app.state.gmail_sync_job = (
            MissingConnectionSyncJob()
        )

        response = client.post(
            "/internal/scheduler/gmail",
            headers=scheduler_headers(),
        )

    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == "Gmail is not connected"
    )