from fastapi.testclient import TestClient

from app.main import app


def test_gmail_status_does_not_expose_secrets() -> None:
    with TestClient(app) as client:
        response = client.get("/gmail/status")

    assert response.status_code == 200
    assert response.json() == {"oauth_configured": False, "connected": False}


def test_gmail_sync_explains_missing_connection() -> None:
    with TestClient(app) as client:
        response = client.post("/internal/scheduler/gmail")

    assert response.status_code == 503
    assert "Gmail is not connected" in response.json()["detail"]
