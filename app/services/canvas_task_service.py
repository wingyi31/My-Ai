from __future__ import annotations

import json
from urllib.parse import urlsplit

from google.cloud import tasks_v2
from google.protobuf import duration_pb2


class CloudTasksNotConfiguredError(
    RuntimeError
):
    pass


class CanvasSyncTaskEnqueuer:

    def __init__(
        self,
        *,
        client: (
            tasks_v2
            .CloudTasksAsyncClient
        ),
        project_id: str,
        location: str,
        queue_name: str,
        worker_base_url: str | None,
        service_account_email: (
            str | None
        ),
        dispatch_deadline_seconds: (
            int
        ) = 1800,
    ) -> None:
        self._client = client
        self._project_id = (
            project_id.strip()
        )
        self._location = location.strip()
        self._queue_name = (
            queue_name.strip()
        )
        self._worker_base_url = (
            worker_base_url.rstrip("/")
            if worker_base_url
            else None
        )
        self._service_account_email = (
            service_account_email.strip()
            if service_account_email
            else None
        )
        self._dispatch_deadline_seconds = (
            dispatch_deadline_seconds
        )

    @property
    def is_configured(self) -> bool:
        return bool(
            self._project_id
            and self._location
            and self._queue_name
            and self._worker_base_url
            and self._service_account_email
        )

    async def enqueue(
        self,
        *,
        canvas_user_id: str,
        course_id: str,
    ) -> dict[str, str]:
        if not canvas_user_id.isdecimal():
            raise ValueError(
                "canvas_user_id must contain "
                "digits only"
            )

        if not course_id.isdecimal():
            raise ValueError(
                "course_id must contain "
                "digits only"
            )

        self._ensure_configured()

        assert (
            self._worker_base_url
            is not None
        )
        assert (
            self._service_account_email
            is not None
        )

        parent = self._client.queue_path(
            self._project_id,
            self._location,
            self._queue_name,
        )

        worker_url = (
            f"{self._worker_base_url}"
            "/internal/canvas/sync"
        )

        request_body = json.dumps(
            {
                "canvas_user_id": (
                    canvas_user_id
                ),
                "course_id": course_id,
            },
            separators=(",", ":"),
        ).encode("utf-8")

        http_request = (
            tasks_v2.HttpRequest(
                http_method=(
                    tasks_v2
                    .HttpMethod.POST
                ),
                url=worker_url,
                headers={
                    "Content-Type": (
                        "application/json"
                    ),
                },
                body=request_body,
                oidc_token=(
                    tasks_v2.OidcToken(
                        service_account_email=(
                            self
                            ._service_account_email
                        ),
                        audience=(
                            self
                            ._worker_base_url
                        ),
                    )
                ),
            )
        )

        task = tasks_v2.Task(
            http_request=http_request,
            dispatch_deadline=(
                duration_pb2.Duration(
                    seconds=(
                        self
                        ._dispatch_deadline_seconds
                    )
                )
            ),
        )

        response = await (
            self._client.create_task(
                request=(
                    tasks_v2
                    .CreateTaskRequest(
                        parent=parent,
                        task=task,
                    )
                )
            )
        )

        return {
            "task_name": response.name,
            "canvas_user_id": (
                canvas_user_id
            ),
            "course_id": course_id,
        }

    def _ensure_configured(
        self,
    ) -> None:
        missing: list[str] = []

        if not self._project_id:
            missing.append(
                "GOOGLE_CLOUD_PROJECT"
            )
        if not self._location:
            missing.append(
                "CLOUD_TASKS_LOCATION"
            )
        if not self._queue_name:
            missing.append(
                "CLOUD_TASKS_QUEUE"
            )
        if not self._worker_base_url:
            missing.append(
                "CLOUD_TASKS_WORKER_BASE_URL"
            )
        if not (
            self._service_account_email
        ):
            missing.append(
                "CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL"
            )

        if missing:
            raise (
                CloudTasksNotConfiguredError(
                    "Missing Cloud Tasks "
                    "configuration: "
                    + ", ".join(missing)
                )
            )

        assert (
            self._worker_base_url
            is not None
        )

        parsed_url = urlsplit(
            self._worker_base_url
        )

        if (
            parsed_url.scheme != "https"
            or not parsed_url.netloc
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise (
                CloudTasksNotConfiguredError(
                    "CLOUD_TASKS_WORKER_BASE_URL "
                    "must be an HTTPS origin"
                )
            )

        if not (
            60
            <= self
            ._dispatch_deadline_seconds
            <= 1800
        ):
            raise (
                CloudTasksNotConfiguredError(
                    "Cloud Tasks dispatch "
                    "deadline must be between "
                    "60 and 1800 seconds"
                )
            )