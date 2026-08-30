import asyncio
import sys

from app.connectors.canvas.client import (
    CanvasReadOnlyClient,
)
from app.connectors.canvas.settings import (
    CanvasSettings,
)


async def main() -> None:
    if len(sys.argv) != 3:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_canvas_file_download "
            "<course_id> <file_id>"
        )

    course_id = sys.argv[1]
    file_id = sys.argv[2]

    settings = CanvasSettings()

    metadata_path = (
        f"courses/{course_id}/files/{file_id}"
    )

    async with CanvasReadOnlyClient(
        base_url=settings.base_url,
        access_token=(
            settings.access_token.get_secret_value()
        ),
    ) as canvas:
        downloaded_file = (
            await canvas.download_file(
                metadata_path
            )
        )

    print("Canvas file download successful")
    print(
        "Canvas file ID:",
        downloaded_file.canvas_file_id,
    )
    print(
        "Filename:",
        downloaded_file.filename,
    )
    print(
        "Content type:",
        downloaded_file.content_type,
    )
    print(
        "Downloaded bytes:",
        downloaded_file.size,
    )


if __name__ == "__main__":
    asyncio.run(main())