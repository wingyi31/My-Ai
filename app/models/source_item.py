from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SourceFileReference(BaseModel):
    canvas_file_id: str | None = None
    link_text: str = ""
    url: str


class NormalizedSourceItem(BaseModel):
    provider: Literal["canvas"] = "canvas"

    source_key: str

    source_type: Literal[
        "page",
        "assignment",
    ]

    academic_category: Literal[
        "lecture",
        "tutorial",
        "assignment",
        "administrative",
        "unknown",
    ] = "unknown"

    course_id: str
    title: str
    body_text: str = ""

    source_url: str | None = None
    source_updated_at: datetime | None = None
    due_at: datetime | None = None
    published: bool | None = None

    module_id: str | None = None
    module_name: str | None = None
    module_item_id: str | None = None
    section_name: str | None = None

    file_references: list[
        SourceFileReference
    ] = Field(default_factory=list)