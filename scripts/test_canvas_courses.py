import asyncio

from app.connectors.canvas.client import (
    CanvasReadOnlyClient,
)
from app.connectors.canvas.discovery import (
    CanvasDiscoveryService,
)
from app.connectors.canvas.settings import (
    CanvasSettings,
)


async def main() -> None:
    settings = CanvasSettings()

    async with CanvasReadOnlyClient(
        base_url=settings.base_url,
        access_token=(
            settings.access_token.get_secret_value()
        ),
    ) as canvas:
        discovery = CanvasDiscoveryService(canvas)
        courses = await discovery.list_active_courses()

    print(f"Active courses found: {len(courses)}")

    for course in courses:
        print(
            {
                "id": course.get("id"),
                "name": course.get("name"),
                "course_code": course.get("course_code"),
                "workflow_state": course.get(
                    "workflow_state"
                ),
                "start_at": course.get("start_at"),
                "end_at": course.get("end_at"),
            }
        )


if __name__ == "__main__":
    asyncio.run(main())