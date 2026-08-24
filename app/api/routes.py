import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.connectors.moodle import MoodleApiError, MoodleNotConfiguredError
from app.core.config import get_settings
from app.services.mytimes_sync import MyTimesSyncService

router = APIRouter()


def verify_scheduler_secret(
    x_scheduler_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Optional local protection; Cloud Run IAM protects this route in production."""
    configured = get_settings().scheduler_shared_secret
    if configured is None:
        return

    expected = configured.get_secret_value()
    if x_scheduler_secret is None or not secrets.compare_digest(
        x_scheduler_secret, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid scheduler secret",
        )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/internal/scheduler/mytimes",
    dependencies=[],
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
