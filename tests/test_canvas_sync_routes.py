from typing import Any

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.routes import (
    canvas_sync as canvas_sync_routes,
)

from app.services.canvas_sync_orchestrator import (
    CanvasSyncAlreadyRunningError,
)


def scheduler_headers() -> dict[str, str]:
    configured_secret = (
        get_settings()
        .scheduler_shared_secret
    )

    if configured_secret is None:
        return {}

    return {
        "X-Scheduler-Secret": (
            configured_secret
            .get_secret_value()
        )
    }


def successful_result() -> dict[str, Any]:
    return {
        "ingestion": {
            "total": 1,
            "unchanged": 1,
        },
        "uploaded_files": 1,
        "pdf_files": 1,
        "non_pdf_files": 0,
        "pdf_processed": 0,
        "pdf_current": 1,
        "pdf_processing_failed": 0,
        "embedding_failed": 0,
        "total_chunks": 14,
        "chunks_embedded": 0,
        "chunks_skipped": 14,
        "empty_chunks": 0,
        "failures": [],
    }


def test_canvas_sync_worker_runs_orchestrator(
    monkeypatch,
) -> None:
    received: dict[str, str] = {}

    async def fake_run_canvas_sync(
        *,
        canvas_user_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        received["canvas_user_id"] = (
            canvas_user_id
        )
        received["course_id"] = course_id

        return successful_result()

    monkeypatch.setattr(
        canvas_sync_routes,
        "run_canvas_sync",
        fake_run_canvas_sync,
    )

    with TestClient(app) as client:
        response = client.post(
            "/internal/canvas/sync",
            headers=scheduler_headers(),
            json={
                "canvas_user_id": "123",
                "course_id": "96996",
            },
        )

    assert response.status_code == 200
    assert response.json() == (
        successful_result()
    )
    assert received == {
        "canvas_user_id": "123",
        "course_id": "96996",
    }


def test_canvas_sync_worker_validates_ids(
    monkeypatch,
) -> None:
    async def should_not_run(
        *,
        canvas_user_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        raise AssertionError(
            "Orchestrator should not run"
        )

    monkeypatch.setattr(
        canvas_sync_routes,
        "run_canvas_sync",
        should_not_run,
    )

    with TestClient(app) as client:
        response = client.post(
            "/internal/canvas/sync",
            headers=scheduler_headers(),
            json={
                "canvas_user_id": (
                    "../invalid"
                ),
                "course_id": "96996",
            },
        )

    assert response.status_code == 422


def test_canvas_sync_worker_requests_retry(
    monkeypatch,
) -> None:
    async def incomplete_sync(
        *,
        canvas_user_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        result = successful_result()
        result["embedding_failed"] = 1
        result["failures"] = [
            {
                "canvas_file_id": "101",
                "stage": "embedding",
                "error_type": (
                    "ClientError"
                ),
                "message": (
                    "Quota exhausted"
                ),
            }
        ]
        return result

    monkeypatch.setattr(
        canvas_sync_routes,
        "run_canvas_sync",
        incomplete_sync,
    )

    with TestClient(app) as client:
        response = client.post(
            "/internal/canvas/sync",
            headers=scheduler_headers(),
            json={
                "canvas_user_id": "123",
                "course_id": "96996",
            },
        )

    assert response.status_code == 503
    assert (
        response.json()["detail"][
            "result"
        ]["embedding_failed"]
        == 1
    )

def test_canvas_sync_worker_handles_duplicate(
    monkeypatch,
) -> None:
    async def already_running(
        *,
        canvas_user_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        raise (
            CanvasSyncAlreadyRunningError(
                "Already running"
            )
        )

    monkeypatch.setattr(
        canvas_sync_routes,
        "run_canvas_sync",
        already_running,
    )

    with TestClient(app) as client:
        response = client.post(
            "/internal/canvas/sync",
            headers=scheduler_headers(),
            json={
                "canvas_user_id": "123",
                "course_id": "96996",
            },
        )

    assert response.status_code == 202
    assert response.json() == {
        "status": "already_running",
        "canvas_user_id": "123",
        "course_id": "96996",
    }