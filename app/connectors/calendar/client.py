from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.connectors.gmail.oauth import (
    GmailCredentialStore,
    GmailNotConfiguredError,
    GmailOAuthClient,
)


GOOGLE_CALENDAR_API_BASE_URL = (
    "https://www.googleapis.com/calendar/v3"
)

EVENT_ID_PATTERN = re.compile(
    r"^[0-9a-v]{5,1024}$"
)


class GoogleCalendarApiError(
    RuntimeError
):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class GoogleCalendarClient:
    """Asynchronous Google Calendar REST client."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        oauth_client: GmailOAuthClient,
        credential_store: (
            GmailCredentialStore
        ),
        calendar_id: str = "primary",
    ) -> None:
        cleaned_calendar_id = (
            calendar_id.strip()
        )

        if not cleaned_calendar_id:
            raise ValueError(
                "Calendar ID cannot be empty"
            )

        self._http_client = http_client
        self._oauth_client = oauth_client
        self._credential_store = (
            credential_store
        )
        self._calendar_id = (
            cleaned_calendar_id
        )

        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    def invalidate_access_token(
        self,
    ) -> None:
        self._access_token = None
        self._access_token_expires_at = 0.0

    async def list_upcoming_events(
        self,
        *,
        max_results: int = 10,
    ) -> dict[str, Any]:
        if not 1 <= max_results <= 100:
            raise ValueError(
                "Maximum results must be "
                "between 1 and 100"
            )

        payload = await self._request(
            "GET",
            self._events_path(),
            params={
                "timeMin": (
                    datetime.now(UTC)
                    .isoformat()
                ),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": max_results,
            },
        )

        raw_items = payload.get(
            "items",
            [],
        )

        if not isinstance(raw_items, list):
            raise GoogleCalendarApiError(
                "Calendar returned an invalid "
                "event list"
            )

        events = [
            item
            for item in raw_items
            if isinstance(item, dict)
        ]

        return {
            "calendar_summary": (
                payload.get("summary")
            ),
            "time_zone": (
                payload.get("timeZone")
            ),
            "access_role": (
                payload.get("accessRole")
            ),
            "events": events,
        }

    async def create_event(
        self,
        *,
        event_id: str,
        event: Mapping[str, Any],
    ) -> dict[str, Any]:
        cleaned_event_id = (
            event_id.strip()
        )

        if not EVENT_ID_PATTERN.fullmatch(
            cleaned_event_id
        ):
            raise ValueError(
                "Calendar event ID must contain "
                "only lowercase base32hex "
                "characters and be between 5 and "
                "1024 characters"
            )

        event_body = dict(event)
        event_body["id"] = cleaned_event_id

        self._validate_event_body(
            event_body
        )

        try:
            return await self._request(
                "POST",
                self._events_path(),
                json_body=event_body,
            )
        except GoogleCalendarApiError as exc:
            if exc.status_code != 409:
                raise

            # A deterministic event ID makes
            # confirmation retries idempotent.
            return await self.get_event(
                cleaned_event_id
            )

    async def get_event(
        self,
        event_id: str,
    ) -> dict[str, Any]:
        cleaned_event_id = event_id.strip()

        if not EVENT_ID_PATTERN.fullmatch(
            cleaned_event_id
        ):
            raise ValueError(
                "Invalid Calendar event ID"
            )

        return await self._request(
            "GET",
            (
                f"{self._events_path()}/"
                f"{quote(cleaned_event_id, safe='')}"
            ),
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[
            str,
            str | int | bool,
        ]
        | None = None,
        json_body: Mapping[
            str,
            Any,
        ]
        | None = None,
    ) -> dict[str, Any]:
        token = await (
            self._get_access_token()
        )

        response = await self._send(
            method,
            path,
            token=token,
            params=params,
            json_body=json_body,
        )

        if response.status_code == 401:
            token = await (
                self._get_access_token(
                    force_refresh=True
                )
            )

            response = await self._send(
                method,
                path,
                token=token,
                params=params,
                json_body=json_body,
            )

        payload = self._decode_payload(
            response
        )

        if response.is_error:
            raise GoogleCalendarApiError(
                self._error_message(
                    payload,
                    response.status_code,
                ),
                status_code=(
                    response.status_code
                ),
            )

        return payload

    async def _send(
        self,
        method: str,
        path: str,
        *,
        token: str,
        params: Mapping[
            str,
            str | int | bool,
        ]
        | None,
        json_body: Mapping[
            str,
            Any,
        ]
        | None,
    ) -> httpx.Response:
        try:
            return await (
                self._http_client.request(
                    method,
                    (
                        f"{GOOGLE_CALENDAR_API_BASE_URL}"
                        f"{path}"
                    ),
                    headers={
                        "Authorization": (
                            f"Bearer {token}"
                        ),
                        "Content-Type": (
                            "application/json"
                        ),
                    },
                    params=params,
                    json=(
                        dict(json_body)
                        if json_body is not None
                        else None
                    ),
                )
            )
        except httpx.HTTPError as exc:
            raise GoogleCalendarApiError(
                "Google Calendar API request "
                f"failed: {exc}"
            ) from exc

    async def _get_access_token(
        self,
        *,
        force_refresh: bool = False,
    ) -> str:
        now = time.monotonic()

        if (
            not force_refresh
            and self._access_token
            and now
            < self._access_token_expires_at
        ):
            return self._access_token

        async with self._token_lock:
            now = time.monotonic()

            if (
                not force_refresh
                and self._access_token
                and now
                < self._access_token_expires_at
            ):
                return self._access_token

            refresh_token = (
                self._credential_store
                .get_refresh_token()
            )

            if not refresh_token:
                raise GmailNotConfiguredError(
                    "Google Calendar is not "
                    "connected. Complete the Google "
                    "OAuth authorization flow."
                )

            tokens = await (
                self._oauth_client
                .refresh_access_token(
                    refresh_token
                )
            )

            self._access_token = (
                tokens.access_token
            )
            self._access_token_expires_at = (
                time.monotonic()
                + max(
                    tokens.expires_in - 60,
                    1,
                )
            )

            return self._access_token

    def _events_path(self) -> str:
        calendar_id = quote(
            self._calendar_id,
            safe="",
        )

        return (
            f"/calendars/{calendar_id}/events"
        )

    @staticmethod
    def _validate_event_body(
        event: Mapping[str, Any],
    ) -> None:
        summary = event.get("summary")
        start = event.get("start")
        end = event.get("end")

        if (
            not isinstance(summary, str)
            or not summary.strip()
        ):
            raise ValueError(
                "Calendar event summary cannot "
                "be empty"
            )

        if not isinstance(start, dict):
            raise ValueError(
                "Calendar event requires a start"
            )

        if not isinstance(end, dict):
            raise ValueError(
                "Calendar event requires an end"
            )

        has_start = bool(
            start.get("dateTime")
            or start.get("date")
        )
        has_end = bool(
            end.get("dateTime")
            or end.get("date")
        )

        if not has_start or not has_end:
            raise ValueError(
                "Calendar event start and end "
                "must contain dateTime or date"
            )

    @staticmethod
    def _decode_payload(
        response: httpx.Response,
    ) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleCalendarApiError(
                "Google Calendar returned a "
                "non-JSON response",
                status_code=(
                    response.status_code
                ),
            ) from exc

        if not isinstance(payload, dict):
            raise GoogleCalendarApiError(
                "Google Calendar returned an "
                "invalid response",
                status_code=(
                    response.status_code
                ),
            )

        return payload

    @staticmethod
    def _error_message(
        payload: dict[str, Any],
        status_code: int,
    ) -> str:
        error = payload.get("error")

        if isinstance(error, dict):
            message = error.get("message")

            if isinstance(message, str):
                return message

        return (
            "Google Calendar rejected the "
            f"request with status {status_code}"
        )