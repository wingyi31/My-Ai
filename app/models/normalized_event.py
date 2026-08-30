from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class EventType(str, Enum):
    ASSIGNMENT = "assignment"
    DEADLINE = "deadline"


class NormalizedEvent(BaseModel):
    source: Literal["mytimes_ical"] = "mytimes_ical"

    # Stable Moodle iCal UID
    external_id: str

    # Hash of UID + source modification time
    revision_key: str

    source_modified_at: datetime

    title: str
    description: str | None = None
    course_name: str | None = None
    event_type: EventType

    due_at: datetime
    all_day: bool = False

    url: str | None = None
    location: str | None = None
    status: str = "CONFIRMED"
    sequence: int = 0


class SyncResult(BaseModel):
    parsed_count: int

    new_count: int
    updated_count: int
    unchanged_count: int

    new: list[NormalizedEvent]
    updated: list[NormalizedEvent]
    unchanged: list[NormalizedEvent]