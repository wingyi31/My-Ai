from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, status

from app.api.routes import verify_scheduler_secret
from app.connectors.canvas import CanvasApiError, CanvasNotConfiguredError
from app.services.canvas_reader import CanvasReadService

router = APIRouter(prefix="/canvas", tags=["Canvas"])
CanvasCourseId = Annotated[str, Path(pattern=r"^\d+$")]


def _reader(request: Request) -> CanvasReadService:
    return CanvasReadService(request.app.state.canvas_client)


def _authorize(secret: str | None) -> None:
    verify_scheduler_secret(secret)


def _raise_canvas_error(exc: Exception) -> None:
    if isinstance(exc, CanvasNotConfiguredError):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_502_BAD_GATEWAY
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/status", summary="Show Canvas reader configuration")
async def canvas_status(
    request: Request,
    x_scheduler_secret: Annotated[str | None, Header()] = None,
) -> dict:
    _authorize(x_scheduler_secret)
    client = request.app.state.canvas_client
    return {
        "configured": client.is_configured,
        "access_mode": "read-only",
        "canvas_base_url": client.base_url,
        "allowed_upstream_method": "GET",
    }


@router.get("/profile", summary="Read the current Canvas profile")
async def canvas_profile(
    request: Request,
    x_scheduler_secret: Annotated[str | None, Header()] = None,
) -> dict:
    _authorize(x_scheduler_secret)
    try:
        return {
            "access_mode": "read-only",
            "profile": await _reader(request).profile(),
        }
    except (CanvasNotConfiguredError, CanvasApiError) as exc:
        _raise_canvas_error(exc)


@router.get("/courses", summary="Read courses available to the Canvas user")
async def canvas_courses(
    request: Request,
    include_completed: Annotated[bool, Query()] = False,
    x_scheduler_secret: Annotated[str | None, Header()] = None,
) -> dict:
    _authorize(x_scheduler_secret)
    try:
        return await _reader(request).courses(include_completed=include_completed)
    except (CanvasNotConfiguredError, CanvasApiError) as exc:
        _raise_canvas_error(exc)


@router.get(
    "/active-courses/details",
    summary="Read details and deadlines for every active Canvas course",
)
async def canvas_active_course_details(
    request: Request,
    x_scheduler_secret: Annotated[str | None, Header()] = None,
) -> dict:
    _authorize(x_scheduler_secret)
    try:
        return await _reader(request).active_course_details()
    except (CanvasNotConfiguredError, CanvasApiError) as exc:
        _raise_canvas_error(exc)


@router.get(
    "/courses/{course_id}/content",
    summary="Read learning materials and deadlines for one Canvas course",
)
async def canvas_course_content(
    request: Request,
    course_id: CanvasCourseId,
    x_scheduler_secret: Annotated[str | None, Header()] = None,
) -> dict:
    _authorize(x_scheduler_secret)
    try:
        return await _reader(request).course_content(course_id)
    except (CanvasNotConfiguredError, CanvasApiError) as exc:
        _raise_canvas_error(exc)
