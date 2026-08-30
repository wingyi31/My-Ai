from __future__ import annotations

from fastapi.responses import JSONResponse

import logging
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel, Field

from app.routes.dependencies import (
    verify_scheduler_secret,
)
from app.services.canvas_sync_orchestrator import (
    CanvasSyncAlreadyRunningError,
    run_canvas_sync,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/canvas",
    tags=["canvas-worker"],
    dependencies=[
        Depends(
            verify_scheduler_secret
        )
    ],
)


class CanvasSyncRequest(BaseModel):
    canvas_user_id: str = Field(
        min_length=1,
        pattern=r"^\d+$",
    )
    course_id: str = Field(
        min_length=1,
        pattern=r"^\d+$",
    )


@router.post(
    "/sync",
    summary=(
        "Synchronize one Canvas course"
    ),
)
async def run_canvas_sync_worker(
    payload: CanvasSyncRequest,
) -> Any:
    try:
        result = await run_canvas_sync(
            canvas_user_id=(
                payload.canvas_user_id
            ),
            course_id=payload.course_id,
        )

    except (
        CanvasSyncAlreadyRunningError
    ):
        return JSONResponse(
            status_code=(
                status.HTTP_202_ACCEPTED
            ),
            content={
                "status": "already_running",
                "canvas_user_id": (
                    payload.canvas_user_id
                ),
                "course_id": (
                    payload.course_id
                ),
            },
        )
    
    except Exception as exc:
        logger.exception(
            "Canvas synchronization "
            "worker failed"
        )

        raise HTTPException(
            status_code=(
                status
                .HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail={
                "message": (
                    "Canvas synchronization "
                    "failed"
                ),
                "error_type": (
                    type(exc).__name__
                ),
            },
        ) from exc

    # Return a retryable HTTP response if
    # embeddings remain incomplete after the
    # embedding service's internal retries.
    if result.get(
        "embedding_failed",
        0,
    ) > 0:
        raise HTTPException(
            status_code=(
                status
                .HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail={
                "message": (
                    "Canvas synchronization "
                    "is incomplete and should "
                    "be retried"
                ),
                "result": result,
            },
        )

    return result