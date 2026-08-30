from app.connectors.canvas.html_parser import (
    parse_canvas_html,
)
from app.models.source_item import (
    NormalizedSourceItem,
    SourceFileReference,
)


def _normalize_file_references(
    links: list[dict],
) -> list[SourceFileReference]:
    references: list[SourceFileReference] = []

    for link in links:
        if link.get("type") != "canvas_file":
            continue

        references.append(
            SourceFileReference(
                canvas_file_id=link.get(
                    "canvas_id"
                ),
                link_text=link.get("text") or "",
                url=link["url"],
            )
        )

    return references


def normalize_page(
    discovered_page: dict,
) -> NormalizedSourceItem:
    return NormalizedSourceItem(
        source_key=discovered_page["source_key"],
        source_type="page",
        academic_category="unknown",
        course_id=str(
            discovered_page["course_id"]
        ),
        title=discovered_page["title"],
        body_text=discovered_page["text"],
        source_url=discovered_page.get(
            "html_url"
        ),
        source_updated_at=discovered_page.get(
            "updated_at"
        ),
        published=discovered_page.get(
            "published"
        ),
        module_id=discovered_page.get(
            "module_id"
        ),
        module_name=discovered_page.get(
            "module_name"
        ),
        module_item_id=str(
            discovered_page["module_item_id"]
        )
        if discovered_page.get("module_item_id")
        else None,
        section_name=discovered_page.get(
            "section_name"
        ),
        file_references=(
            _normalize_file_references(
                discovered_page.get("links", [])
            )
        ),
    )


def normalize_assignment(
    assignment: dict,
    course_id: str,
    canvas_base_url: str,
) -> NormalizedSourceItem:
    description_html = (
        assignment.get("description") or ""
    )

    parsed = parse_canvas_html(
        html=description_html,
        base_url=canvas_base_url,
    )

    assignment_id = str(assignment["id"])

    return NormalizedSourceItem(
        source_key=(
            f"canvas:{course_id}:"
            f"assignment:{assignment_id}"
        ),
        source_type="assignment",
        academic_category="assignment",
        course_id=course_id,
        title=assignment.get("name") or "",
        body_text=parsed["text"],
        source_url=assignment.get("html_url"),
        source_updated_at=assignment.get(
            "updated_at"
        ),
        due_at=assignment.get("due_at"),
        published=assignment.get("published"),
        file_references=(
            _normalize_file_references(
                parsed["links"]
            )
        ),
    )