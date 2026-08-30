import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.connectors.gmail.oauth import (
    GMAIL_READONLY_SCOPE,
    GOOGLE_OAUTH_SCOPES,
    GmailCredentialStore,
    GmailOAuthClient,
    InvalidOAuthStateError,
    OAuthStateSigner,
)


def test_state_signer_detects_tampering() -> None:
    signer = OAuthStateSigner("test-state-secret")
    state = signer.issue()

    signer.verify(state)
    with pytest.raises(InvalidOAuthStateError):
        signer.verify(state + "tampered")


def test_local_credential_store_round_trip(tmp_path) -> None:
    path = tmp_path / "gmail.json"
    store = GmailCredentialStore(configured_refresh_token=None, path=path)

    assert store.get_refresh_token() is None
    store.save_refresh_token("refresh-token")

    assert store.get_refresh_token() == "refresh-token"
    assert path.stat().st_mode & 0o777 == 0o600


def test_authorization_url_and_code_exchange() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/token"
            return httpx.Response(
                200,
                json={
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                    "scope": GOOGLE_OAUTH_SCOPES,
                    "token_type": "Bearer",
                },
            )

        signer = OAuthStateSigner("test-state-secret")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            oauth = GmailOAuthClient(
                http_client=client,
                client_id="client-id",
                client_secret="client-secret",
                redirect_uri="http://localhost/gmail/oauth/callback",
                state_signer=signer,
            )
            url = oauth.authorization_url()
            query = parse_qs(urlparse(url).query)
            assert query["scope"] == [
                GOOGLE_OAUTH_SCOPES
            ]            
            assert query["access_type"] == ["offline"]

            tokens = await oauth.exchange_code(
                code="authorization-code",
                state=query["state"][0],
            )

        assert tokens.access_token == "access-token"
        assert tokens.refresh_token == "refresh-token"

    asyncio.run(run())
