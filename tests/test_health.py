from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def scheduler_headers() -> dict[str, str]:
    configured_secret = get_settings().scheduler_shared_secret

    if configured_secret is None:
        return {}

    return {
        "X-Scheduler-Secret": configured_secret.get_secret_value()
    }


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_scheduler_explains_missing_token() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/internal/scheduler/mytimes",
            headers=scheduler_headers(),
        )

    assert response.status_code == 503
    assert "MYTIMES_TOKEN is missing" in response.json()["detail"]