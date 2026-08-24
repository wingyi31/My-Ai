from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx


class CanvasNotConfiguredError(RuntimeError):
    pass


class CanvasApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CanvasClient:
    """Read-only client for the Canvas LMS REST API.

    The public surface intentionally exposes only operations backed by Canvas
    GET endpoints. There are no generic request, write, submit, upload, or
    mark-as-read methods.
    """

    _MAX_PAGES = 100
    _MODULE_ITEM_CONCURRENCY = 5

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        base_url: str,
        access_key: str | None,
    ) -> None:
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")
        self._access_key = access_key

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._access_key)

    async def get_current_user(self) -> dict[str, Any]:
        payload = await self._get_json("/api/v1/users/self/profile")
        if not isinstance(payload, dict):
            raise CanvasApiError("Canvas returned an unexpected profile response")
        return payload

    async def list_courses(
        self,
        *,
        include_completed: bool = False,
    ) -> list[dict[str, Any]]:
        parameters: dict[str, Any] = {
            "include[]": ["term", "favorites"],
            "per_page": 100,
        }
        if include_completed:
            parameters["state[]"] = ["available", "completed"]
        else:
            parameters["enrollment_state"] = "active"
            parameters["state[]"] = "available"

        return await self._get_paginated("/api/v1/courses", params=parameters)

    async def get_course(self, course_id: str | int) -> dict[str, Any]:
        course_id = self._validated_id(course_id)
        payload = await self._get_json(
            f"/api/v1/courses/{course_id}",
            params={"include[]": ["term"]},
        )
        if not isinstance(payload, dict):
            raise CanvasApiError("Canvas returned an unexpected course response")
        return payload

    async def list_modules(self, course_id: str | int) -> list[dict[str, Any]]:
        course_id = self._validated_id(course_id)
        modules = await self._get_paginated(
            f"/api/v1/courses/{course_id}/modules",
            params={
                "include[]": ["items", "content_details"],
                "per_page": 100,
            },
        )

        # Canvas may omit inline items for a large module. Fill only those gaps.
        semaphore = asyncio.Semaphore(self._MODULE_ITEM_CONCURRENCY)

        async def fill_items(module: dict[str, Any]) -> None:
            if isinstance(module.get("items"), list):
                return
            module_id = module.get("id")
            if module_id is not None:
                async with semaphore:
                    module["items"] = await self.list_module_items(
                        course_id,
                        module_id,
                    )

        await asyncio.gather(*(fill_items(module) for module in modules))
        return modules

    async def list_module_items(
        self,
        course_id: str | int,
        module_id: str | int,
    ) -> list[dict[str, Any]]:
        course_id = self._validated_id(course_id)
        module_id = self._validated_id(module_id)
        return await self._get_paginated(
            f"/api/v1/courses/{course_id}/modules/{module_id}/items",
            params={"include[]": "content_details", "per_page": 100},
        )

    async def list_assignments(
        self,
        course_id: str | int,
    ) -> list[dict[str, Any]]:
        course_id = self._validated_id(course_id)
        return await self._get_paginated(
            f"/api/v1/courses/{course_id}/assignments",
            params={"order_by": "due_at", "per_page": 100},
        )

    async def list_quizzes(self, course_id: str | int) -> list[dict[str, Any]]:
        course_id = self._validated_id(course_id)
        return await self._get_paginated(
            f"/api/v1/courses/{course_id}/quizzes",
            params={"per_page": 100},
        )

    async def list_announcements(
        self,
        course_id: str | int,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        course_id = self._validated_id(course_id)
        parameters: dict[str, Any] = {
            "context_codes[]": f"course_{course_id}",
            "active_only": True,
            "latest_only": False,
            "per_page": 100,
        }
        if start_date:
            parameters["start_date"] = start_date
        if end_date:
            parameters["end_date"] = end_date
        return await self._get_paginated(
            "/api/v1/announcements",
            params=parameters,
        )

    async def list_files(self, course_id: str | int) -> list[dict[str, Any]]:
        course_id = self._validated_id(course_id)
        return await self._get_paginated(
            f"/api/v1/courses/{course_id}/files",
            params={"sort": "updated_at", "order": "desc", "per_page": 100},
        )

    async def _get_paginated(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        url = self._api_url(path)
        page_params = params
        records: list[dict[str, Any]] = []

        for _ in range(self._MAX_PAGES):
            response = await self._get_response(url, params=page_params)
            payload = self._json(response)
            if not isinstance(payload, list) or not all(
                isinstance(item, dict) for item in payload
            ):
                raise CanvasApiError(
                    f"Canvas returned an unexpected list response for {path}"
                )
            records.extend(payload)

            next_link = response.links.get("next")
            if not next_link or not next_link.get("url"):
                return records

            url = self._validated_next_url(next_link["url"])
            page_params = None

        raise CanvasApiError(
            f"Canvas pagination exceeded {self._MAX_PAGES} pages for {path}"
        )

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self._json(await self._get_response(self._api_url(path), params=params))

    async def _get_response(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self._ensure_configured()
        try:
            response = await self._http_client.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {self._access_key}",
                    "Accept": "application/json+canvas-string-ids",
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 401:
                message = "Canvas rejected the access key (401 Unauthorized)"
            elif status_code == 403:
                message = "Canvas denied read access to this resource (403 Forbidden)"
            elif status_code == 404:
                message = "Canvas could not find this resource (404 Not Found)"
            else:
                message = f"Canvas returned HTTP {status_code}"
            raise CanvasApiError(message, status_code=status_code) from exc
        except httpx.HTTPError as exc:
            raise CanvasApiError(f"Canvas request failed: {exc}") from exc
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise CanvasApiError("Canvas returned a non-JSON response") from exc

    def _ensure_configured(self) -> None:
        if not self._base_url:
            raise CanvasNotConfiguredError("CANVAS_BASE_URL is missing")
        if not self._access_key:
            raise CanvasNotConfiguredError("CANVAS_ACCESS_KEY is missing")
        parsed_base_url = urlsplit(self._base_url)
        if parsed_base_url.scheme != "https" or not parsed_base_url.netloc:
            raise CanvasNotConfiguredError(
                "CANVAS_BASE_URL must be an HTTPS Canvas origin"
            )

    def _api_url(self, path: str) -> str:
        if not path.startswith("/api/v1/"):
            raise ValueError("Canvas API paths must stay under /api/v1/")
        return f"{self._base_url}{path}"

    def _validated_next_url(self, url: str) -> str:
        base = urlsplit(self._base_url)
        candidate = urlsplit(url)
        if (
            candidate.scheme != base.scheme
            or candidate.netloc != base.netloc
            or not candidate.path.startswith("/api/v1/")
        ):
            raise CanvasApiError("Canvas returned an unsafe pagination URL")
        return url

    @staticmethod
    def _validated_id(value: str | int) -> str:
        text = str(value)
        if not text.isdecimal():
            raise ValueError("Canvas IDs must contain digits only")
        return text
