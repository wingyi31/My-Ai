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
    session_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
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
    session_id: str
    tool_calls: list[
        AgentToolCallResponse
    ]
    sources: list[RagSourceResponse]
    pending_action: (
        PendingCalendarActionResponse | None
    ) = None

class ConversationSummaryResponse(
    BaseModel
):
    session_id: str
    course_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationMessageResponse(
    BaseModel
):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ConversationHistoryResponse(
    BaseModel
):
    session_id: str
    course_id: str
    messages: list[
        ConversationMessageResponse
    ]

class SummaryPreferencesUpdateRequest(
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
    session_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    detail_level: Literal[
        "concise",
        "balanced",
        "detailed",
    ]
    section_order: list[str] = Field(
        min_length=1,
        max_length=12,
    )
    preferred_language: str = Field(
        min_length=1,
        max_length=50,
    )
    include_flashcards: bool = True
    include_source_links: bool = True


class SummaryPreferencesResponse(
    BaseModel
):
    user_id: str
    detail_level: Literal[
        "concise",
        "balanced",
        "detailed",
    ]
    section_order: list[str]
    preferred_language: str
    include_flashcards: bool
    include_source_links: bool
    version: int
    confirmed: bool
    updated_at: datetime | None

class TopicSummaryPrepareRequest(
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
    session_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    topic: str = Field(
        min_length=1,
        max_length=500,
    )
    source_limit: int = Field(
        default=10,
        ge=1,
        le=20,
    )


class TopicSummaryResponse(BaseModel):
    summary_id: str
    topic: str
    summary: str
    generation_model: str
    preference_version: int
    preferences_confirmed: bool
    section_order: list[str]
    sources: list[RagSourceResponse]
    created_at: datetime


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