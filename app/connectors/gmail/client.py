from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

import httpx

from app.connectors.gmail.oauth import (
    GmailCredentialStore,
    GmailNotConfiguredError,
    GmailOAuthClient,
)

GMAIL_API_BASE_URL = "https://gmail.googleapis.com/gmail/v1"


class GmailApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GmailHistoryExpiredError(GmailApiError):
    """The saved Gmail history ID is too old and a new bootstrap is required."""


@dataclass(frozen=True, slots=True)
class MessageListPage:
    message_ids: tuple[str, ...]
    next_page_token: str | None
    result_size_estimate: int


@dataclass(frozen=True, slots=True)
class HistoryListPage:
    history: tuple[dict[str, Any], ...]
    next_page_token: str | None
    latest_history_id: str


class GmailClient:
    """Small asynchronous Gmail REST client with refresh-token authentication."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        oauth_client: GmailOAuthClient,
        credential_store: GmailCredentialStore,
        user_id: str = "me",
    ) -> None:
        self._http_client = http_client
        self._oauth_client = oauth_client
        self._credential_store = credential_store
        self._user_id = user_id
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    def invalidate_access_token(self) -> None:
        self._access_token = None
        self._access_token_expires_at = 0.0

    async def get_profile(self) -> dict[str, Any]:
        payload = await self._request("GET", self._user_path("profile"))
        if not isinstance(payload.get("emailAddress"), str):
            raise GmailApiError("Gmail profile response had no emailAddress")
        if not isinstance(payload.get("historyId"), str):
            raise GmailApiError("Gmail profile response had no historyId")
        return payload

    async def list_messages(
        self,
        *,
        query: str,
        max_results: int,
        page_token: str | None = None,
    ) -> MessageListPage:
        params: dict[str, str | int] = {
            "q": query,
            "maxResults": min(max(max_results, 1), 500),
        }
        if page_token:
            params["pageToken"] = page_token
        payload = await self._request(
            "GET",
            self._user_path("messages"),
            params=params,
        )
        raw_messages = payload.get("messages", [])
        if not isinstance(raw_messages, list):
            raise GmailApiError("Gmail message-list response was invalid")
        message_ids = tuple(
            item["id"]
            for item in raw_messages
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
        next_page_token = payload.get("nextPageToken")
        estimate = payload.get("resultSizeEstimate", len(message_ids))
        return MessageListPage(
            message_ids=message_ids,
            next_page_token=(
                next_page_token if isinstance(next_page_token, str) else None
            ),
            result_size_estimate=estimate
            if isinstance(estimate, int)
            else len(message_ids),
        )

    async def get_message(self, message_id: str) -> dict[str, Any]:
        payload = await self._request(
            "GET",
            self._user_path(f"messages/{quote(message_id, safe='')}"),
            params={"format": "full"},
        )
        if not isinstance(payload.get("id"), str):
            raise GmailApiError(f"Gmail returned an invalid message for {message_id}")
        return payload

    async def list_history(
        self,
        *,
        start_history_id: str,
        page_token: str | None = None,
        label_id: str = "INBOX",
        max_results: int = 500,
    ) -> HistoryListPage:
        params: dict[str, str | int] = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "labelId": label_id,
            "maxResults": min(max(max_results, 1), 500),
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            payload = await self._request(
                "GET",
                self._user_path("history"),
                params=params,
            )
        except GmailApiError as exc:
            if exc.status_code == 404:
                raise GmailHistoryExpiredError(
                    "The saved Gmail history ID has expired; a full bootstrap is required",
                    status_code=404,
                ) from exc
            raise

        raw_history = payload.get("history", [])
        latest_history_id = payload.get("historyId")
        if not isinstance(raw_history, list) or not isinstance(latest_history_id, str):
            raise GmailApiError("Gmail history response was invalid")
        history = tuple(item for item in raw_history if isinstance(item, dict))
        next_page_token = payload.get("nextPageToken")
        return HistoryListPage(
            history=history,
            next_page_token=(
                next_page_token if isinstance(next_page_token, str) else None
            ),
            latest_history_id=latest_history_id,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> dict[str, Any]:
        token = await self._get_access_token()
        response = await self._send(method, path, token=token, params=params)
        if response.status_code == 401:
            token = await self._get_access_token(force_refresh=True)
            response = await self._send(method, path, token=token, params=params)

        payload = self._decode_payload(response)
        if response.is_error:
            message = self._error_message(payload, response.status_code)
            raise GmailApiError(message, status_code=response.status_code)
        return payload

    async def _send(
        self,
        method: str,
        path: str,
        *,
        token: str,
        params: Mapping[str, str | int] | None,
    ) -> httpx.Response:
        try:
            return await self._http_client.request(
                method,
                f"{GMAIL_API_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
        except httpx.HTTPError as exc:
            raise GmailApiError(f"Gmail API request failed: {exc}") from exc

    async def _get_access_token(self, *, force_refresh: bool = False) -> str:
        now = time.monotonic()
        if (
            not force_refresh
            and self._access_token
            and now < self._access_token_expires_at
        ):
            return self._access_token

        async with self._token_lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._access_token
                and now < self._access_token_expires_at
            ):
                return self._access_token

            refresh_token = self._credential_store.get_refresh_token()
            if not refresh_token:
                raise GmailNotConfiguredError(
                    "Gmail is not connected. Visit /gmail/oauth/authorize or set "
                    "GMAIL_REFRESH_TOKEN."
                )
            tokens = await self._oauth_client.refresh_access_token(refresh_token)
            self._access_token = tokens.access_token
            self._access_token_expires_at = time.monotonic() + max(
                tokens.expires_in - 60,
                1,
            )
            return self._access_token

    def _user_path(self, suffix: str) -> str:
        user_id = quote(self._user_id, safe="")
        return f"/users/{user_id}/{suffix}"

    @staticmethod
    def _decode_payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise GmailApiError(
                f"Gmail API returned non-JSON (HTTP {response.status_code})",
                status_code=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise GmailApiError(
                "Gmail API returned an invalid response",
                status_code=response.status_code,
            )
        return payload

    @staticmethod
    def _error_message(payload: dict[str, Any], status_code: int) -> str:
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            detail = error["message"]
        else:
            detail = "request rejected"
        return f"Gmail API error (HTTP {status_code}): {detail}"
