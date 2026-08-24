from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class GmailNotConfiguredError(RuntimeError):
    """Raised when required Gmail OAuth settings or credentials are absent."""


class GmailOAuthError(RuntimeError):
    """Raised when Google rejects an OAuth request or returns an invalid payload."""


class InvalidOAuthStateError(GmailOAuthError):
    """Raised when the signed OAuth state is invalid or expired."""


@dataclass(frozen=True, slots=True)
class OAuthTokens:
    access_token: str
    expires_in: int
    refresh_token: str | None = None
    token_type: str = "Bearer"
    scope: str | None = None


class GmailCredentialStore:
    """Resolve a refresh token from the environment or a local, ignored file.

    The file makes the browser callback useful during local development. Production
    deployments should inject ``GMAIL_REFRESH_TOKEN`` from a secret manager because
    a Cloud Run filesystem is ephemeral.
    """

    def __init__(
        self,
        *,
        configured_refresh_token: str | None,
        path: Path,
    ) -> None:
        self._configured_refresh_token = configured_refresh_token
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def get_refresh_token(self) -> str | None:
        if self._configured_refresh_token:
            return self._configured_refresh_token
        if not self._path.exists():
            return None

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GmailOAuthError(
                f"Could not read Gmail credentials from {self._path}"
            ) from exc

        token = payload.get("refresh_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise GmailOAuthError(
                f"Gmail credential file {self._path} has no refresh_token"
            )
        return token

    def has_refresh_token(self) -> bool:
        return self.get_refresh_token() is not None

    def save_refresh_token(self, refresh_token: str) -> None:
        if not refresh_token:
            raise GmailOAuthError("Google did not provide a usable refresh token")

        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"refresh_token": refresh_token}, indent=2) + "\n"
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                temporary_file.write(payload)
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._path)
        except OSError as exc:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
            raise GmailOAuthError(
                f"Could not save Gmail credentials to {self._path}"
            ) from exc


class OAuthStateSigner:
    """Issue short-lived, signed state values for the OAuth redirect round-trip."""

    def __init__(self, secret: str | None, *, max_age_seconds: int = 600) -> None:
        self._secret = secret.encode("utf-8") if secret else None
        self._max_age_seconds = max_age_seconds

    def issue(self) -> str:
        if not self._secret:
            raise GmailNotConfiguredError(
                "GMAIL_OAUTH_STATE_SECRET is required before starting OAuth"
            )
        issued_at = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        value = f"{issued_at}.{nonce}"
        signature = self._sign(value)
        return f"{value}.{signature}"

    def verify(self, state: str) -> None:
        if not self._secret:
            raise GmailNotConfiguredError(
                "GMAIL_OAUTH_STATE_SECRET is required before completing OAuth"
            )
        try:
            issued_at_text, nonce, signature = state.split(".", 2)
            issued_at = int(issued_at_text)
        except (AttributeError, TypeError, ValueError) as exc:
            raise InvalidOAuthStateError("Invalid Gmail OAuth state") from exc

        value = f"{issued_at_text}.{nonce}"
        expected = self._sign(value)
        age = int(time.time()) - issued_at
        if (
            not nonce
            or not hmac.compare_digest(signature, expected)
            or age < -30
            or age > self._max_age_seconds
        ):
            raise InvalidOAuthStateError("Gmail OAuth state is invalid or expired")

    def _sign(self, value: str) -> str:
        assert self._secret is not None
        digest = hmac.new(self._secret, value.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class GmailOAuthClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        client_id: str | None,
        client_secret: str | None,
        redirect_uri: str,
        state_signer: OAuthStateSigner,
    ) -> None:
        self._http_client = http_client
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._state_signer = state_signer

    @property
    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret and self._redirect_uri)

    def authorization_url(self) -> str:
        self._require_configuration()
        state = self._state_signer.issue()
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": GMAIL_READONLY_SCOPE,
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "state": state,
            }
        )
        return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{query}"

    async def exchange_code(self, *, code: str, state: str) -> OAuthTokens:
        self._require_configuration()
        self._state_signer.verify(state)
        return await self._token_request(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self._redirect_uri,
            }
        )

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        self._require_configuration()
        if not refresh_token:
            raise GmailNotConfiguredError(
                "Gmail is not connected. Complete /gmail/oauth/authorize or set "
                "GMAIL_REFRESH_TOKEN."
            )
        return await self._token_request(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        )

    async def _token_request(self, form: dict[str, str | None]) -> OAuthTokens:
        try:
            response = await self._http_client.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={key: value for key, value in form.items() if value is not None},
            )
        except httpx.HTTPError as exc:
            raise GmailOAuthError(f"Google OAuth request failed: {exc}") from exc

        payload = self._decode_payload(response)
        if response.is_error:
            error = payload.get("error", "unknown_error")
            description = payload.get("error_description", "Google rejected OAuth")
            raise GmailOAuthError(f"Google OAuth error [{error}]: {description}")

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GmailOAuthError("Google OAuth response had no access_token")

        expires_in = payload.get("expires_in", 3600)
        try:
            expires_in = int(expires_in)
        except (TypeError, ValueError) as exc:
            raise GmailOAuthError(
                "Google OAuth response had an invalid expires_in"
            ) from exc

        refresh_token = payload.get("refresh_token")
        scope = payload.get("scope")
        token_type = payload.get("token_type", "Bearer")
        return OAuthTokens(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token if isinstance(refresh_token, str) else None,
            token_type=token_type if isinstance(token_type, str) else "Bearer",
            scope=scope if isinstance(scope, str) else None,
        )

    @staticmethod
    def _decode_payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise GmailOAuthError("Google OAuth returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise GmailOAuthError("Google OAuth returned an invalid response")
        return payload

    def _require_configuration(self) -> None:
        if not self.is_configured:
            raise GmailNotConfiguredError(
                "GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET are required"
            )
