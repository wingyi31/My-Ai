from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter(
    include_in_schema=False
)

STATIC_DIRECTORY = (
    Path(__file__).resolve()
    .parent.parent
    / "static"
)


@router.get("/")
async def studyops_ui() -> FileResponse:
    return FileResponse(
        STATIC_DIRECTORY / "index.html"
    )