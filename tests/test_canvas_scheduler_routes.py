from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


class FakeCanvasTaskEnqueuer:

    def __init__(self) -> None:
        self.received: dict[
            str,
            str,
        ] = {}

    async def enqueue(
        self,
        *,
        canvas_user_id: str,
        course_id: str,
    ) -> dict[str, str]:
        self.received = {
            "canvas_user_id": (
                canvas_user_id
            ),
            "course_id": course_id,
        }

        return {
            "task_name": (
                "projects/test/locations/"
                "test/queues/test/"
                "tasks/task-1"
            ),
            "canvas_user_id": (
                canvas_user_id
            ),
            "course_id": course_id,
        }


def scheduler_headers() -> dict[str, str]:
    secret = (
        get_settings()
        .scheduler_shared_secret
    )

    if secret is None:
        return {}

    return {
        "X-Scheduler-Secret": (
            secret.get_secret_value()
        )
    }


def test_canvas_scheduler_enqueues_task() -> None:
    fake_enqueuer = (
        FakeCanvasTaskEnqueuer()
    )

    with TestClient(app) as client:
        app.state.canvas_task_enqueuer = (
            fake_enqueuer
        )

        response = client.post(
            "/internal/scheduler/canvas",
            headers=scheduler_headers(),
            json={
                "canvas_user_id": "123",
                "course_id": "96996",
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == (
        "enqueued"
    )
    assert fake_enqueuer.received == {
        "canvas_user_id": "123",
        "course_id": "96996",
    }