import asyncio
import sys

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
    if len(sys.argv) != 2:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_canvas_assignments "
            "<course_id>"
        )

    course_id = sys.argv[1]
    settings = CanvasSettings()

    async with CanvasReadOnlyClient(
        base_url=settings.base_url,
        access_token=(
            settings.access_token.get_secret_value()
        ),
    ) as canvas:
        discovery = CanvasDiscoveryService(canvas)

        assignments = await discovery.list_assignments(
            course_id=course_id,
        )

    print(
        f"Assignments found for course "
        f"{course_id}: {len(assignments)}"
    )

    for assignment in assignments:
        print(
            {
                "id": assignment.get("id"),
                "name": assignment.get("name"),
                "due_at": assignment.get("due_at"),
                "unlock_at": assignment.get("unlock_at"),
                "lock_at": assignment.get("lock_at"),
                "updated_at": assignment.get(
                    "updated_at"
                ),
                "published": assignment.get(
                    "published"
                ),
                "submission_types": assignment.get(
                    "submission_types"
                ),
                "html_url": assignment.get(
                    "html_url"
                ),
            }
        )


if __name__ == "__main__":
    asyncio.run(main())