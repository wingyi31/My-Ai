from dataclasses import dataclass
from typing import Any

import httpx


class CanvasReadOnlyViolation(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CanvasDownloadedFile:
    canvas_file_id: str
    filename: str
    content_type: str
    content: bytes

    @property
    def size(self) -> int:
        return len(self.content)


class CanvasReadOnlyClient:
    def __init__(
        self,
        base_url: str,
        access_token: str,
    ):
        api_base_url = (
            f"{base_url.rstrip('/')}/api/v1/"
        )

        self._canvas_host = (
            httpx.URL(api_base_url).host.lower()
        )

        self._http = httpx.AsyncClient(
            base_url=api_base_url,
            headers={
                "Authorization": (
                    f"Bearer {access_token}"
                ),
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            event_hooks={
                "request": [
                    self._enforce_read_only
                ],
            },
        )

    @staticmethod
    async def _enforce_read_only(
        request: httpx.Request,
    ) -> None:
        if request.method.upper() != "GET":
            raise CanvasReadOnlyViolation(
                "Blocked non-GET request to Canvas: "
                f"{request.method} {request.url}"
            )

    async def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        response = await self._http.get(
            path.lstrip("/"),
            params=params,
        )

        response.raise_for_status()
        return response.json()

    async def download_file(
        self,
        metadata_path: str,
    ) -> CanvasDownloadedFile:
        metadata = await self.get_json(
            metadata_path
        )

        if not isinstance(metadata, dict):
            raise TypeError(
                "Expected Canvas file metadata "
                "to be a dictionary"
            )

        download_url = metadata.get("url")

        if not download_url:
            raise RuntimeError(
                "Canvas file metadata does not "
                "contain a download URL"
            )

        canvas_file_id = str(
            metadata.get("id", "")
        )

        filename = str(
            metadata.get("display_name")
            or metadata.get("filename")
            or f"{canvas_file_id}.bin"
        )

        response = await self._download_url(
            str(download_url)
        )

        response.raise_for_status()

        content = response.content

        if not content:
            raise RuntimeError(
                f"Canvas returned an empty file: "
                f"{filename}"
            )

        response_content_type = (
            response.headers
            .get("content-type", "")
            .split(";", maxsplit=1)[0]
            .strip()
            .lower()
        )

        metadata_content_type = str(
            metadata.get("content-type", "")
        ).lower()

        content_type = (
            response_content_type
            or metadata_content_type
            or "application/octet-stream"
        )

        if content_type in {
            "application/json",
            "text/html",
        }:
            raise RuntimeError(
                "Canvas returned a webpage or JSON "
                f"instead of file bytes: {filename}"
            )

        is_pdf = (
            filename.lower().endswith(".pdf")
            or content_type == "application/pdf"
        )

        if (
            is_pdf
            and b"%PDF-" not in content[:1024]
        ):
            raise RuntimeError(
                "Downloaded content does not appear "
                f"to be a valid PDF: {filename}"
            )

        return CanvasDownloadedFile(
            canvas_file_id=canvas_file_id,
            filename=filename,
            content_type=content_type,
            content=content,
        )

    async def _download_url(
        self,
        download_url: str,
    ) -> httpx.Response:
        target = httpx.URL(download_url)
        target_host = target.host.lower()

        headers = {
            "Accept": (
                "application/pdf,"
                "application/octet-stream,"
                "*/*"
            )
        }

        # Use the authenticated client only when the
        # initial download URL belongs to Canvas.
        if target_host == self._canvas_host:
            return await self._http.get(
                download_url,
                headers=headers,
                timeout=60.0,
            )

        # Never send the Canvas token to another host.
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=60.0,
            headers=headers,
        ) as public_http:
            return await public_http.get(
                download_url
            )

    async def get_paginated(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        next_url: str | None = path.lstrip("/")
        next_params = params
        seen_urls: set[str] = set()

        for page_number in range(1, 51):
            print(
                f"Requesting Canvas page "
                f"{page_number}..."
            )

            try:
                response = await self._http.get(
                    next_url,
                    params=next_params,
                    timeout=15.0,
                )
            except httpx.TimeoutException as exc:
                raise RuntimeError(
                    "Canvas request timed out "
                    "after 15 seconds"
                ) from exc

            requested_url = str(
                response.request.url
            )

            print(
                "Canvas response: "
                f"status={response.status_code}, "
                f"url={requested_url}"
            )

            if requested_url in seen_urls:
                raise RuntimeError(
                    "Canvas pagination loop "
                    f"detected: {requested_url}"
                )

            seen_urls.add(requested_url)
            response.raise_for_status()

            page = response.json()

            if not isinstance(page, list):
                raise TypeError(
                    "Expected Canvas to return "
                    "a list, received "
                    f"{type(page).__name__}"
                )

            print(
                f"Items received on page: "
                f"{len(page)}"
            )

            items.extend(page)

            next_link = response.links.get("next")

            if not next_link or not page:
                print(
                    "No next page. "
                    "Pagination completed."
                )
                return items

            next_url = next_link.get("url")

            if not next_url:
                return items

            next_params = None

        raise RuntimeError(
            "Canvas pagination exceeded the "
            "50-page safety limit"
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(
        self,
    ) -> "CanvasReadOnlyClient":
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        await self.close()