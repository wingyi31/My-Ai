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
            "scripts.test_canvas_modules "
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
            course_id=course_id,
        )

        print(
            f"Modules found for course "
            f"{course_id}: {len(modules)}"
        )

        total_items = 0
        file_items = 0

        for module in modules:
            module_id = str(module["id"])

            print()
            print(
                {
                    "module_id": module_id,
                    "module_name": module.get("name"),
                    "position": module.get("position"),
                    "published": module.get("published"),
                }
            )

            items = await discovery.list_module_items(
                course_id=course_id,
                module_id=module_id,
            )

            total_items += len(items)

            for item in items:
                item_type = item.get("type")

                if item_type == "File":
                    file_items += 1

                print(
                    {
                        "item_id": item.get("id"),
                        "title": item.get("title"),
                        "type": item_type,
                        "content_id": item.get(
                            "content_id"
                        ),
                        "page_url": item.get(
                            "page_url"
                        ),
                        "url": item.get("url"),
                        "html_url": item.get(
                            "html_url"
                        ),
                        "published": item.get(
                            "published"
                        ),
                    }
                )

    print()
    print("Total module items:", total_items)
    print("File items found:", file_items)


if __name__ == "__main__":
    asyncio.run(main())