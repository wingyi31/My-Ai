from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def scheduler_headers() -> dict[str, str]:
    configured_secret = get_settings().scheduler_shared_secret
    if configured_secret is None:
        return {}
    return {"X-Scheduler-Secret": configured_secret.get_secret_value()}


def test_canvas_status_reports_read_only_configuration() -> None:
    with TestClient(app) as client:
        response = client.get("/canvas/status", headers=scheduler_headers())

    assert response.status_code == 200
    assert response.json()["access_mode"] == "read-only"
    assert response.json()["allowed_upstream_method"] == "GET"
    assert "access_key" not in response.text.casefold()


def test_canvas_route_rejects_non_numeric_course_id() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/canvas/courses/not-a-course/content",
            headers=scheduler_headers(),
        )

    assert response.status_code == 422


def test_canvas_routes_do_not_expose_write_methods() -> None:
    with TestClient(app) as client:
        response = client.post("/canvas/courses", headers=scheduler_headers())

    assert response.status_code == 405


def test_active_course_details_route_is_get_only() -> None:
    operation = app.openapi()["paths"]["/canvas/active-courses/details"]

    assert set(operation) == {"get"}
