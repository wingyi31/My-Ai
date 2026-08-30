from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class NotionError(RuntimeError):
    pass


class NotionNotConfiguredError(
    NotionError
):
    pass


class NotionApiError(NotionError):

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


@dataclass(frozen=True)
class NotionConnectionInfo:
    user_id: str
    name: str | None
    user_type: str


@dataclass(frozen=True)
class NotionPage:
    page_id: str
    url: str
    title: str


class NotionClient:

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        api_key: str | None,
        api_version: str = "2026-03-11",
        base_url: str = (
            "https://api.notion.com/v1"
        ),
        parent_page_id: str | None = None,
    ) -> None:
        self._http_client = http_client
        self._api_key = (
            api_key.strip()
            if api_key is not None
            else None
        )
        self._api_version = (
            api_version.strip()
        )
        self._base_url = (
            base_url.rstrip("/")
        )
        self._parent_page_id = (
            parent_page_id.strip()
            if parent_page_id is not None
            else None
        )

        if not self._api_version:
            raise ValueError(
                "Notion API version cannot be "
                "empty"
            )

        if not self._base_url:
            raise ValueError(
                "Notion base URL cannot be empty"
            )

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def is_write_configured(self) -> bool:
        return bool(
            self._api_key
            and self._parent_page_id
        )

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise NotionNotConfiguredError(
                "NOTION_API_KEY is not configured"
            )

        return {
            "Authorization": (
                f"Bearer {self._api_key}"
            ),
            "Notion-Version": (
                self._api_version
            ),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await (
                self._http_client.request(
                    method,
                    (
                        f"{self._base_url}/"
                        f"{path.lstrip('/')}"
                    ),
                    headers=self._headers(),
                    json=json,
                )
            )
        except httpx.HTTPError as error:
            raise NotionApiError(
                "Could not reach the Notion API"
            ) from error

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.is_error:
            error_code = (
                payload.get("code")
                if isinstance(payload, dict)
                and isinstance(
                    payload.get("code"),
                    str,
                )
                else None
            )
            message = (
                payload.get("message")
                if isinstance(payload, dict)
                and isinstance(
                    payload.get("message"),
                    str,
                )
                else (
                    "Notion API request failed "
                    f"with status "
                    f"{response.status_code}"
                )
            )

            raise NotionApiError(
                message,
                status_code=(
                    response.status_code
                ),
                error_code=error_code,
            )

        if not isinstance(payload, dict):
            raise NotionApiError(
                "Notion returned an invalid response",
                status_code=response.status_code,
            )

        return payload

    async def verify_connection(
        self,
    ) -> NotionConnectionInfo:
        payload = await self._request(
            "GET",
            "/users/me",
        )

        user_id = payload.get("id")
        user_type = payload.get("type")
        name = payload.get("name")

        if (
            not isinstance(user_id, str)
            or not user_id
            or not isinstance(
                user_type,
                str,
            )
        ):
            raise NotionApiError(
                "Notion returned invalid user data"
            )

        return NotionConnectionInfo(
            user_id=user_id,
            name=(
                name
                if isinstance(name, str)
                else None
            ),
            user_type=user_type,
        )

    async def verify_parent_access(
        self,
    ) -> bool:
        if not self._parent_page_id:
            raise NotionNotConfiguredError(
                "NOTION_PARENT_PAGE_ID is not "
                "configured"
            )

        payload = await self._request(
            "GET",
            (
                f"/pages/"
                f"{self._parent_page_id}"
            ),
        )

        page_id = payload.get("id")

        if (
            not isinstance(page_id, str)
            or not page_id
        ):
            raise NotionApiError(
                "Notion returned invalid parent "
                "page data"
            )

        return True

    async def create_markdown_page(
        self,
        *,
        title: str,
        markdown: str,
    ) -> NotionPage:
        cleaned_title = title.strip()
        cleaned_markdown = markdown.strip()

        if not cleaned_title:
            raise ValueError(
                "Notion page title cannot be empty"
            )

        if not cleaned_markdown:
            raise ValueError(
                "Notion page content cannot be "
                "empty"
            )
        
        if not self._parent_page_id:
            raise NotionNotConfiguredError(
                "NOTION_PARENT_PAGE_ID is not "
                "configured"
            )

        payload = await self._request(
            "POST",
            "/pages",
            json={
                "parent": {
                    "page_id": (
                        self._parent_page_id
                    ),
                },
                "icon": {
                    "emoji": "🎓",
                },
                "markdown": (
                    f"# {cleaned_title}\n\n"
                    f"{cleaned_markdown}"
                ),
            },
        )

        page_id = payload.get("id")
        url = payload.get("url")

        if (
            not isinstance(page_id, str)
            or not page_id
            or not isinstance(url, str)
            or not url
        ):
            raise NotionApiError(
                "Notion returned invalid page data"
            )

        return NotionPage(
            page_id=page_id,
            url=url,
            title=cleaned_title,
        )