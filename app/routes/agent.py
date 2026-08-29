from typing import Annotated

from fastapi import (
    APIRouter,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)

from app.connectors.calendar import (
    GoogleCalendarApiError,
)
from app.connectors.canvas import (
    CanvasApiError,
    CanvasNotConfiguredError,
)
from app.connectors.gmail.oauth import (
    GmailNotConfiguredError,
    GmailOAuthError,
)
from app.models.agent import (
    ActionUserRequest,
    AgentChatRequest,
    AgentChatResponse,
    AgentToolCallResponse,
    CalendarActionCancelResponse,
    CalendarActionConfirmationResponse,
    CalendarActionPrepareRequest,
    PendingCalendarActionResponse,
    ConversationHistoryResponse,
    ConversationMessageResponse,
    ConversationSummaryResponse,
    SummaryPreferencesResponse,
    SummaryPreferencesUpdateRequest,
)
from app.models.rag import RagSourceResponse
from app.repositories.pending_action_repository import (
    PendingActionExpiredError,
    PendingActionNotFoundError,
    PendingActionStateError,
    PendingCalendarAction,
)
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.episodic_memory_repository import (
    EpisodicMemoryRepository,
)
from app.repositories.summary_preference_repository import (
    SummaryPreferenceError,
    SummaryPreferenceRepository,
    SummaryPreferences,
)
from app.services.academic_agent_service import (
    AcademicAgentService,
)
from app.services.calendar_action_service import (
    CalendarActionService,
)


router = APIRouter(
    prefix="/api/v1/agent",
    tags=["agent"],
)

ActionId = Annotated[
    str,
    Path(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]
SessionId = Annotated[
    str,
    Path(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]

UserIdQuery = Annotated[
    str,
    Query(
        min_length=1,
        max_length=200,
    ),
]

CourseIdQuery = Annotated[
    str,
    Query(
        min_length=1,
        max_length=200,
    ),
]


def get_agent_service(
    request: Request,
) -> AcademicAgentService:
    service = getattr(
        request.app.state,
        "academic_agent_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Academic agent service is not ready"
            ),
        )

    return service

def get_conversation_repository(
    request: Request,
) -> ConversationRepository:
    repository = getattr(
        request.app.state,
        "conversation_repository",
        None,
    )

    if repository is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Conversation repository is not "
                "ready"
            ),
        )

    return repository

def get_episodic_memory_repository(
    request: Request,
) -> EpisodicMemoryRepository:
    repository = getattr(
        request.app.state,
        "episodic_memory_repository",
        None,
    )

    if repository is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Episodic memory repository is "
                "not ready"
            ),
        )

    return repository


def get_summary_preference_repository(
    request: Request,
) -> SummaryPreferenceRepository:
    repository = getattr(
        request.app.state,
        "summary_preference_repository",
        None,
    )

    if repository is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Summary preference repository "
                "is not ready"
            ),
        )

    return repository


def get_calendar_action_service(
    request: Request,
) -> CalendarActionService:
    service = getattr(
        request.app.state,
        "calendar_action_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Calendar action service is not "
                "ready"
            ),
        )

    return service


def pending_action_response(
    action: PendingCalendarAction,
) -> PendingCalendarActionResponse:
    return PendingCalendarActionResponse(
        action_id=action.action_id,
        user_id=action.user_id,
        course_id=action.course_id,
        action_type=action.action_type,
        status=action.status,
        event_id=action.event_id,
        event=action.event,
        source=action.source,
        created_at=action.created_at,
        expires_at=action.expires_at,
        completed_at=action.completed_at,
        calendar_event_id=(
            action.calendar_event_id
        ),
        calendar_event_link=(
            action.calendar_event_link
        ),
    )

@router.get(
    "/conversations",
    response_model=list[
        ConversationSummaryResponse
    ],
)
async def list_conversations(
    request: Request,
    user_id: UserIdQuery,
    course_id: CourseIdQuery,
    limit: Annotated[
        int,
        Query(ge=1, le=50),
    ] = 20,
) -> list[ConversationSummaryResponse]:
    repository = (
        get_conversation_repository(request)
    )

    try:
        conversations = (
            await repository.list_conversations(
                user_id=user_id,
                course_id=course_id,
                limit=limit,
            )
        )
    except ValueError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(error),
        ) from error

    return [
        ConversationSummaryResponse(
            session_id=conversation.session_id,
            course_id=conversation.course_id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
        for conversation in conversations
    ]


@router.get(
    "/conversations/{session_id}/messages",
    response_model=ConversationHistoryResponse,
)
async def get_conversation_messages(
    request: Request,
    session_id: SessionId,
    user_id: UserIdQuery,
    course_id: CourseIdQuery,
) -> ConversationHistoryResponse:
    repository = (
        get_conversation_repository(request)
    )

    try:
        messages = (
            await repository
            .load_recent_messages(
                user_id=user_id,
                course_id=course_id,
                session_id=session_id,
                limit=100,
            )
        )
    except ValueError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(error),
        ) from error

    return ConversationHistoryResponse(
        session_id=session_id,
        course_id=course_id,
        messages=[
            ConversationMessageResponse(
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )

@router.get(
    "/preferences/summary",
    response_model=(
        SummaryPreferencesResponse
    ),
)
async def get_summary_preferences(
    request: Request,
    user_id: UserIdQuery,
) -> SummaryPreferencesResponse:
    repository = (
        get_summary_preference_repository(
            request
        )
    )

    try:
        preferences = await (
            repository.get_summary_preferences(
                user_id=user_id
            )
        )
    except SummaryPreferenceError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(error),
        ) from error

    return summary_preferences_response(
        preferences
    )


@router.put(
    "/preferences/summary",
    response_model=(
        SummaryPreferencesResponse
    ),
)
async def update_summary_preferences(
    payload: SummaryPreferencesUpdateRequest,
    request: Request,
) -> SummaryPreferencesResponse:
    preference_repository = (
        get_summary_preference_repository(
            request
        )
    )
    episodic_repository = (
        get_episodic_memory_repository(
            request
        )
    )

    try:
        preferences = await (
            preference_repository
            .save_summary_preferences(
                user_id=payload.user_id,
                detail_level=(
                    payload.detail_level
                ),
                section_order=(
                    payload.section_order
                ),
                preferred_language=(
                    payload.preferred_language
                ),
                include_flashcards=(
                    payload.include_flashcards
                ),
                include_source_links=(
                    payload.include_source_links
                ),
            )
        )

        await episodic_repository.record_event(
            user_id=payload.user_id,
            course_id=payload.course_id,
            session_id=payload.session_id,
            event_type=(
                "preference.summary_confirmed"
            ),
            entity_type=(
                "summary_preferences"
            ),
            entity_id=str(
                preferences.version
            ),
            payload={
                "detail_level": (
                    preferences.detail_level
                ),
                "section_order": list(
                    preferences.section_order
                ),
                "preferred_language": (
                    preferences
                    .preferred_language
                ),
            },
        )
    except ValueError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(error),
        ) from error

    return summary_preferences_response(
        preferences
    )

@router.post(
    "/chat",
    response_model=AgentChatResponse,
)
async def chat_with_agent(
    payload: AgentChatRequest,
    request: Request,
) -> AgentChatResponse:
    service = get_agent_service(request)

    try:
        result = await service.chat(
            user_id=payload.user_id,
            course_id=payload.course_id,
            session_id=payload.session_id,
            message=payload.message,
            source_limit=payload.source_limit,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(error),
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=str(error),
        ) from error

    sources = [
        RagSourceResponse(
            source_number=source_number,
            chunk_id=source.chunk_id,
            document_path=(
                source.document_path
            ),
            canvas_file_id=(
                source.canvas_file_id
            ),
            filename=source.filename,
            page_number=source.page_number,
            chunk_index=source.chunk_index,
            similarity=source.similarity,
            distance=source.distance,
        )
        for source_number, source in enumerate(
            result.sources,
            start=1,
        )
    ]

    tool_calls = [
        AgentToolCallResponse(
            name=tool_call.name,
            arguments=tool_call.arguments,
        )
        for tool_call in result.tool_calls
    ]

    return AgentChatResponse(
        message=result.message,
        session_id=payload.session_id,
        answer=result.answer,
        generation_model=(
            result.generation_model
        ),
        tool_calls=tool_calls,
        sources=sources,
        pending_action=(
            pending_action_response(
                result.pending_action
            )
            if result.pending_action
            is not None
            else None
        ),
    )

def pending_action_response(
    action: PendingCalendarAction,
) -> PendingCalendarActionResponse:
    return PendingCalendarActionResponse(
        # Existing fields remain here
    )


def summary_preferences_response(
    preferences: SummaryPreferences,
) -> SummaryPreferencesResponse:
    return SummaryPreferencesResponse(
        user_id=preferences.user_id,
        detail_level=(
            preferences.detail_level
        ),
        section_order=list(
            preferences.section_order
        ),
        preferred_language=(
            preferences.preferred_language
        ),
        include_flashcards=(
            preferences.include_flashcards
        ),
        include_source_links=(
            preferences.include_source_links
        ),
        version=preferences.version,
        confirmed=preferences.confirmed,
        updated_at=preferences.updated_at,
    )


@router.get(
    "/conversations",
    # Existing route continues here
)


@router.post(
    "/actions/calendar/prepare",
    response_model=(
        PendingCalendarActionResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
)
async def prepare_calendar_action(
    payload: CalendarActionPrepareRequest,
    request: Request,
) -> PendingCalendarActionResponse:
    service = get_calendar_action_service(
        request
    )

    try:
        action = await (
            service.prepare_assignment_event(
                user_id=payload.user_id,
                course_id=payload.course_id,
                assignment_query=(
                    payload.assignment_query
                ),
                date_field=(
                    payload.date_field
                ),
            )
        )
    except ValueError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(error),
        ) from error
    except CanvasNotConfiguredError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=str(error),
        ) from error
    except CanvasApiError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=str(error),
        ) from error

    return pending_action_response(action)


@router.post(
    "/actions/{action_id}/confirm",
    response_model=(
        CalendarActionConfirmationResponse
    ),
)
async def confirm_calendar_action(
    action_id: ActionId,
    payload: ActionUserRequest,
    request: Request,
) -> CalendarActionConfirmationResponse:
    service = get_calendar_action_service(
        request
    )

    try:
        result = await service.confirm_action(
            user_id=payload.user_id,
            action_id=action_id,
        )
    except PendingActionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except (
        PendingActionExpiredError,
        PendingActionStateError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except GmailNotConfiguredError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=str(error),
        ) from error
    except (
        GmailOAuthError,
        GoogleCalendarApiError,
    ) as error:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(error),
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=str(error),
        ) from error

    return CalendarActionConfirmationResponse(
        status=result.action.status,
        already_completed=(
            result.already_completed
        ),
        action=pending_action_response(
            result.action
        ),
    )


@router.post(
    "/actions/{action_id}/cancel",
    response_model=(
        CalendarActionCancelResponse
    ),
)
async def cancel_calendar_action(
    action_id: ActionId,
    payload: ActionUserRequest,
    request: Request,
) -> CalendarActionCancelResponse:
    service = get_calendar_action_service(
        request
    )

    try:
        await service.cancel_action(
            user_id=payload.user_id,
            action_id=action_id,
        )
    except PendingActionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except PendingActionStateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    return CalendarActionCancelResponse(
        status="cancelled",
        action_id=action_id,
    )