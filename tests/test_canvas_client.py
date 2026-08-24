import asyncio

import httpx
import pytest

from app.connectors.canvas import (
    CanvasApiError,
    CanvasClient,
    CanvasNotConfiguredError,
)


def test_canvas_client_uses_get_and_follows_safe_pagination() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert request.method == "GET"
            assert request.headers["Authorization"] == "Bearer secret"
            assert request.headers["Accept"] == "application/json+canvas-string-ids"
            if request.url.params.get("page") == "2":
                return httpx.Response(200, json=[{"id": "2", "name": "Two"}])
            return httpx.Response(
                200,
                json=[{"id": "1", "name": "One"}],
                headers={
                    "Link": '<https://canvas.example.edu/api/v1/courses?page=2>; rel="next"'
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = CanvasClient(
                http_client,
                "https://canvas.example.edu",
                "secret",
            )
            courses = await client.list_courses()

        assert [course["id"] for course in courses] == ["1", "2"]
        assert len(requests) == 2
        assert requests[0].url.params["enrollment_state"] == "active"

    asyncio.run(run())


def test_canvas_client_rejects_cross_origin_pagination() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[],
                headers={
                    "Link": '<https://attacker.example/api/v1/courses?page=2>; rel="next"'
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = CanvasClient(
                http_client,
                "https://canvas.example.edu",
                "secret",
            )
            with pytest.raises(CanvasApiError, match="unsafe pagination"):
                await client.list_courses()

    asyncio.run(run())


def test_canvas_client_explains_missing_access_key() -> None:
    async def run() -> None:
        async with httpx.AsyncClient() as http_client:
            client = CanvasClient(
                http_client,
                "https://canvas.example.edu",
                None,
            )
            with pytest.raises(
                CanvasNotConfiguredError,
                match="CANVAS_ACCESS_KEY is missing",
            ):
                await client.get_current_user()

    asyncio.run(run())


def test_canvas_client_rejects_non_numeric_ids_before_request() -> None:
    async def run() -> None:
        async with httpx.AsyncClient() as http_client:
            client = CanvasClient(
                http_client,
                "https://canvas.example.edu",
                "secret",
            )
            with pytest.raises(ValueError, match="digits only"):
                await client.list_assignments("../users/self")

    asyncio.run(run())


def test_canvas_client_lists_quizzes_and_course_announcements_with_get() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=[])

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = CanvasClient(
                http_client,
                "https://canvas.example.edu",
                "secret",
            )
            await client.list_quizzes("42")
            await client.list_announcements(
                "42",
                start_date="2026-08-01T00:00:00Z",
                end_date="2026-08-31T00:00:00Z",
            )

        assert [request.method for request in requests] == ["GET", "GET"]
        assert requests[0].url.path == "/api/v1/courses/42/quizzes"
        assert requests[1].url.path == "/api/v1/announcements"
        assert requests[1].url.params["context_codes[]"] == "course_42"
        assert requests[1].url.params["active_only"] == "true"
        assert requests[1].url.params["latest_only"] == "false"

    asyncio.run(run())


def test_canvas_api_error_keeps_http_status_for_optional_resources() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"errors": [{"message": "missing"}]})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = CanvasClient(
                http_client,
                "https://canvas.example.edu",
                "secret",
            )
            with pytest.raises(CanvasApiError) as error:
                await client.list_quizzes("42")

        assert error.value.status_code == 404

    asyncio.run(run())
