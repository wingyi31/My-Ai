from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.rag import RagSourceResponse


AssignmentDateField = Literal[
    "due_at",
    "lock_at",
    "unlock_at",
]


class AgentChatRequest(BaseModel):
    user_id: str = Field(
        min_length=1,
        max_length=200,
    )
    course_id: str = Field(
        min_length=1,
        max_length=200,
    )
    message: str = Field(
        min_length=1,
        max_length=8000,
    )
    source_limit: int | None = Field(
        default=None,
        ge=1,
        le=20,
    )


class AgentToolCallResponse(BaseModel):
    name: str
    arguments: dict[str, Any]


class CalendarActionPrepareRequest(
    BaseModel
):
    user_id: str = Field(
        min_length=1,
        max_length=200,
    )
    course_id: str = Field(
        min_length=1,
        max_length=200,
    )
    assignment_query: str = Field(
        min_length=1,
        max_length=500,
    )
    date_field: AssignmentDateField = (
        "due_at"
    )


class ActionUserRequest(BaseModel):
    user_id: str = Field(
        min_length=1,
        max_length=200,
    )


class PendingCalendarActionResponse(
    BaseModel
):
    action_id: str
    user_id: str
    course_id: str
    action_type: str
    status: str
    event_id: str
    event: dict[str, Any]
    source: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    completed_at: datetime | None
    calendar_event_id: str | None
    calendar_event_link: str | None


class AgentChatResponse(BaseModel):
    message: str
    answer: str
    generation_model: str
    tool_calls: list[
        AgentToolCallResponse
    ]
    sources: list[RagSourceResponse]
    pending_action: (
        PendingCalendarActionResponse | None
    ) = None


class CalendarActionConfirmationResponse(
    BaseModel
):
    status: str
    already_completed: bool
    action: PendingCalendarActionResponse


class CalendarActionCancelResponse(
    BaseModel
):
    status: str
    action_id: str