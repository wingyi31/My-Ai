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
from app.connectors.canvas.html_parser import (
    parse_canvas_html,
)


async def main() -> None:
    if len(sys.argv) != 2:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_canvas_page "
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

        modules = await discovery.list_modules(
            course_id
        )

        for module in modules:
            module_id = str(module["id"])

            items = await discovery.list_module_items(
                course_id=course_id,
                module_id=module_id,
            )

            for item in items:
                if item.get("type") != "Page":
                    continue

                page_url = item.get("page_url")

                if not page_url:
                    continue

                page = await discovery.get_page(
                    course_id=course_id,
                    page_url=page_url,
                )

                body = page.get("body") or ""

                #Keep the existing page metadata output
                parsed = parse_canvas_html(
                    html=body,
                    base_url=str(settings.base_url),
                )

                print()
                print("Parsed Canvas page")
                print(
                    {
                        "visible_text_length": len(
                            parsed["text"]
                        ),
                        "links_found": len(
                            parsed["links"]
                        ),
                        "text_preview": parsed["text"][:300],
                    }
                )

                for link in parsed["links"]:
                    print(
                        {
                            "type": link["type"],
                            "canvas_id": link["canvas_id"],
                            "text": link["text"][:100],
                            "url": link["url"],
                        }
                    )

                print("Canvas page retrieved")
                print(
                    {
                        "course_id": course_id,
                        "module_id": module_id,
                        "module_name": module.get("name"),
                        "module_item_id": item.get("id"),
                        "page_id": page.get("page_id"),
                        "page_url": page.get("url"),
                        "title": page.get("title"),
                        "published": page.get(
                            "published"
                        ),
                        "created_at": page.get(
                            "created_at"
                        ),
                        "updated_at": page.get(
                            "updated_at"
                        ),
                        "body_length": len(body),
                        "has_body": bool(body.strip()),
                    }
                )

                # Test only the first page.
                return

        print("No Canvas Page item was found.")


if __name__ == "__main__":
    asyncio.run(main())