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
from app.connectors.canvas.normalizer import (
    normalize_assignment,
    normalize_page,
)
from app.connectors.canvas.settings import (
    CanvasSettings,
)
from app.connectors.canvas.deduplicator import (
    decide_change,
)


async def main() -> None:
    if len(sys.argv) != 2:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_canvas_normalization "
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

        pages = await scanner.scan_pages(course_id)

        assignments = (
            await discovery.list_assignments(
                course_id
            )
        )

    normalized_pages = [
        normalize_page(page)
        for page in pages
    ]

    normalized_assignments = [
        normalize_assignment(
            assignment=assignment,
            course_id=course_id,
            canvas_base_url=str(
                settings.base_url
            ),
        )
        for assignment in assignments
    ]

    normalized_items = (
        normalized_pages
        + normalized_assignments
    )

    stored_hashes: dict[str, str] = {}

    print()
    print("First synchronization:")

    for item in normalized_items:
        result = decide_change(
            item=item,
            existing_revision_hash=(
                stored_hashes.get(item.source_key)
            ),
        )

        print(
            item.title,
            "->",
            result.change_type.value,
        )

        stored_hashes[item.source_key] = (
            result.revision_hash
        )

    print()
    print("Second synchronization:")

    for item in normalized_items:
        result = decide_change(
            item=item,
            existing_revision_hash=(
                stored_hashes.get(item.source_key)
            ),
        )

        print(
            item.title,
            "->",
            result.change_type.value,
        )

    if normalized_items:
        original = normalized_items[0]

        modified = original.model_copy(
            update={
                "title": (
                    original.title
                    + " - changed"
                )
            }
        )

        result = decide_change(
            item=modified,
            existing_revision_hash=(
                stored_hashes[
                    original.source_key
                ]
            ),
        )

        print()
        print("Simulated Canvas revision:")
        print(
            modified.title,
            "->",
            result.change_type.value,
        )

    print()
    print(
        "Normalized Pages:",
        len(normalized_pages),
    )
    print(
        "Normalized Assignments:",
        len(normalized_assignments),
    )
    print(
        "Total normalized sources:",
        len(normalized_items),
    )

    print()
    print("Normalized source summary:")

    for item in normalized_items:
        print(
            {
                "source_key": item.source_key,
                "source_type": item.source_type,
                "category": (
                    item.academic_category
                ),
                "title": item.title,
                "text_length": len(
                    item.body_text
                ),
                "due_at": item.due_at,
                "file_count": len(
                    item.file_references
                ),
            }
        )

        if item.file_references:
            print(
                "File references for:",
                item.title,
            )

            for reference in item.file_references:
                print(
                    reference.model_dump(
                        mode="json"
                    )
                )


if __name__ == "__main__":
    asyncio.run(main())