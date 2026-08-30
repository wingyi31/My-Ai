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
    if len(sys.argv) != 3:
        raise RuntimeError(
        "Usage: python -m "
        "scripts.test_canvas_file_metadata "
        "<course_id> <file_id>"
    )

    course_id = sys.argv[1]
    file_id = sys.argv[2]
    settings = CanvasSettings()

    async with CanvasReadOnlyClient(
        base_url=settings.base_url,
        access_token=(
            settings.access_token.get_secret_value()
        ),
    ) as canvas:
        discovery = CanvasDiscoveryService(canvas)

        metadata = await discovery.get_file_metadata(
            course_id=course_id,
            file_id=file_id,
        )

    print("File metadata retrieved")
    print(
        {
            "file_id": metadata.get("id"),
            "display_name": metadata.get(
                "display_name"
            ),
            "filename": metadata.get("filename"),
            "content_type": metadata.get(
                "content-type"
            ),
            "size": metadata.get("size"),
            "created_at": metadata.get(
                "created_at"
            ),
            "updated_at": metadata.get(
                "updated_at"
            ),
            "locked": metadata.get("locked"),
            "hidden": metadata.get("hidden"),
            "has_download_url": bool(
                metadata.get("url")
            ),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())