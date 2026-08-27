from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from google.api_core.exceptions import (
    GoogleAPICallError,
)
from pydantic import BaseModel, Field

from app.routes.dependencies import (
    verify_scheduler_secret,
)
from app.services.canvas_task_service import (
    CloudTasksNotConfiguredError,
)


router = APIRouter(
    prefix="/internal/scheduler",
    tags=["canvas-scheduler"],
    dependencies=[
        Depends(
            verify_scheduler_secret
        )
    ],
)


class CanvasScheduleRequest(BaseModel):
    canvas_user_id: str = Field(
        min_length=1,
        pattern=r"^\d+$",
    )
    course_id: str = Field(
        min_length=1,
        pattern=r"^\d+$",
    )


@router.post(
    "/canvas",
    status_code=(
        status.HTTP_202_ACCEPTED
    ),
    summary=(
        "Enqueue one Canvas course sync"
    ),
)
async def enqueue_canvas_sync(
    payload: CanvasScheduleRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        task = await (
            request.app.state
            .canvas_task_enqueuer
            .enqueue(
                canvas_user_id=(
                    payload.canvas_user_id
                ),
                course_id=(
                    payload.course_id
                ),
            )
        )
    except (
        CloudTasksNotConfiguredError
    ) as exc:
        raise HTTPException(
            status_code=(
                status
                .HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=str(exc),
        ) from exc
    except GoogleAPICallError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "Cloud Tasks rejected the "
                "enqueue request"
            ),
        ) from exc

    return {
        "status": "enqueued",
        **task,
    }