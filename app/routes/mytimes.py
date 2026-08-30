from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.connectors.moodle import MoodleApiError, MoodleNotConfiguredError
from app.routes.dependencies import verify_scheduler_secret
from app.services.mytimes_sync import MyTimesSyncService

router = APIRouter(tags=["MyTIMeS"])


@router.post(
    "/internal/scheduler/mytimes",
    summary="Run one MyTIMeS metadata synchronization",
)
async def run_mytimes_sync(
    request: Request,
    x_scheduler_secret: Annotated[str | None, Header()] = None,
) -> dict:
    verify_scheduler_secret(x_scheduler_secret)
    service = MyTimesSyncService(request.app.state.moodle_client)

    try:
        return await service.preview_metadata_sync()
    except MoodleNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except MoodleApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
