from app.connectors.canvas.discovery import (
    CanvasDiscoveryService,
)
from app.connectors.canvas.html_parser import (
    parse_canvas_html,
)

#Scans every page, not only the first page
class CanvasCourseScanner:
    def __init__(
        self,
        discovery: CanvasDiscoveryService,
        base_url: str,
    ):
        self._discovery = discovery
        self._base_url = base_url

    async def scan_pages(
        self,
        course_id: str,
    ) -> list[dict]:
        discovered_pages: list[dict] = []

        modules = await self._discovery.list_modules(
            course_id
        )

        for module in modules:
            module_id = str(module["id"])
            current_subheader: str | None = None

            items = (
                await self._discovery.list_module_items(
                    course_id=course_id,
                    module_id=module_id,
                )
            )

            for item in items:
                item_type = item.get("type")

                if item_type == "SubHeader":
                    current_subheader = item.get("title")
                    continue

                if item_type != "Page":
                    continue

                page_url = item.get("page_url")

                if not page_url:
                    continue

                page = await self._discovery.get_page(
                    course_id=course_id,
                    page_url=page_url,
                )

                body_html = page.get("body") or ""

                parsed = parse_canvas_html(
                    html=body_html,
                    base_url=self._base_url,
                )

                file_links = [
                    link
                    for link in parsed["links"]
                    if link["type"] == "canvas_file"
                ]

                page_id = (
                    page.get("page_id")
                    or page.get("url")
                )

                discovered_pages.append(
                    {
                        "source_key": (
                            f"canvas:{course_id}:"
                            f"page:{page_id}"
                        ),
                        "canvas_type": "Page",
                        "course_id": course_id,
                        "html_url": page.get("html_url"),
                        "module_id": module_id,
                        "module_name": module.get("name"),
                        "module_position": module.get(
                            "position"
                        ),
                        "section_name": current_subheader,
                        "module_item_id": item.get("id"),
                        "item_position": item.get(
                            "position"
                        ),
                        "page_id": page_id,
                        "page_url": page.get("url"),
                        "title": page.get("title"),
                        "published": page.get(
                            "published"
                        ),
                        "updated_at": page.get(
                            "updated_at"
                        ),
                        "text": parsed["text"],
                        "links": parsed["links"],
                        "file_links": file_links,
                    }
                )

        return discovered_pages