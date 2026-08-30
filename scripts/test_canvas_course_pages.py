import asyncio
import sys

from app.connectors.canvas.client import (
    CanvasReadOnlyClient,
)
from app.connectors.canvas.course_scanner import (
    CanvasCourseScanner,
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
            "scripts.test_canvas_course_pages "
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

        scanner = CanvasCourseScanner(
            discovery=discovery,
            base_url=str(settings.base_url),
        )

        pages = await scanner.scan_pages(
            course_id=course_id
        )

    print()
    print(f"Total Pages discovered: {len(pages)}")

    for index, page in enumerate(pages, start=1):
        print()
        print(
            {
                "number": index,
                "module": page["module_name"],
                "section": page["section_name"],
                "title": page["title"],
                "page_id": page["page_id"],
                "text_length": len(page["text"]),
                "file_count": len(
                    page["file_links"]
                ),
                "file_ids": [
                    link["canvas_id"]
                    for link in page["file_links"]
                ],
            }
        )


if __name__ == "__main__":
    asyncio.run(main())