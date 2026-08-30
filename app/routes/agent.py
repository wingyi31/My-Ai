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
from app.connectors.notion.client import (
    NotionApiError,
    NotionClient,
    NotionNotConfiguredError,
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
    TopicSummaryPrepareRequest,
    TopicSummaryResponse,
    NotionPublishCancelResponse,
    NotionPublishConfirmationResponse,
    NotionPublishPrepareRequest,
    PendingNotionActionResponse,
)
from app.models.rag import RagSourceResponse
from app.repositories.pending_action_repository import (
    PendingActionExpiredError,
    PendingActionNotFoundError,
    PendingActionStateError,
    PendingCalendarAction,
)
from app.repositories.pending_notion_action_repository import (
    CANCELLED_STATUS as NOTION_CANCELLED_STATUS,
    COMPLETED_STATUS as NOTION_COMPLETED_STATUS,
    PendingNotionAction,
    PendingNotionActionError,
    PendingNotionActionExpiredError,
    PendingNotionActionNotFoundError,
    PendingNotionActionRepository,
    PendingNotionActionStateError,
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
from app.repositories.episodic_memory_repository import (
    EpisodicEventNotFoundError,
    EpisodicMemoryRepository,
)
from app.repositories.pending_notion_action_repository import (
    PendingNotionAction,
    PendingNotionActionError,
    PendingNotionActionRepository,
)
from app.services.academic_agent_service import (
    AcademicAgentService,
)
from app.services.calendar_action_service import (
    CalendarActionService,
)
from app.services.rag_answer_service import (
    RagAnswerService,
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

def get_pending_notion_action_repository(
    request: Request,
) -> PendingNotionActionRepository:
    repository = getattr(
        request.app.state,
        "pending_notion_action_repository",
        None,
    )

    if repository is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Pending Notion action repository "
                "is not ready"
            ),
        )

    return repository

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

def get_notion_client(
    request: Request,
) -> NotionClient:
    client = getattr(
        request.app.state,
        "notion_client",
        None,
    )

    if client is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="Notion client is not ready",
        )

    return client


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

def pending_notion_action_response(
    action: PendingNotionAction,
) -> PendingNotionActionResponse:
    return PendingNotionActionResponse(
        action_id=action.action_id,
        user_id=action.user_id,
        course_id=action.course_id,
        session_id=action.session_id,
        action_type=action.action_type,
        summary_id=action.summary_id,
        title=action.title,
        status=action.status,
        created_at=action.created_at,
        expires_at=action.expires_at,
        completed_at=action.completed_at,
        notion_page_id=(
            action.notion_page_id
        ),
        notion_page_url=(
            action.notion_page_url
        ),
        failed_attempts=(
            action.failed_attempts
        ),
        last_error=action.last_error,
    )

def get_rag_answer_service(
    request: Request,
) -> RagAnswerService:
    service = getattr(
        request.app.state,
        "rag_answer_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "RAG answer service is not ready"
            ),
        )

    return service

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
    "/summaries/prepare",
    response_model=TopicSummaryResponse,
    status_code=(
        status.HTTP_201_CREATED
    ),
)
async def prepare_topic_summary(
    payload: TopicSummaryPrepareRequest,
    request: Request,
) -> TopicSummaryResponse:
    rag_service = get_rag_answer_service(
        request
    )
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
            .get_summary_preferences(
                user_id=payload.user_id
            )
        )

        result = await (
            rag_service.generate_topic_summary(
                user_id=payload.user_id,
                course_id=payload.course_id,
                topic=payload.topic,
                detail_level=(
                    preferences.detail_level
                ),
                section_order=(
                    preferences.section_order
                ),
                preferred_language=(
                    preferences
                    .preferred_language
                ),
                include_flashcards=(
                    preferences
                    .include_flashcards
                ),
                include_source_links=(
                    preferences
                    .include_source_links
                ),
                source_limit=(
                    payload.source_limit
                ),
            )
        )

        source_payload = [
            {
                "source_number": source_number,
                "chunk_id": source.chunk_id,
                "document_path": (
                    source.document_path
                ),
                "canvas_file_id": (
                    source.canvas_file_id
                ),
                "filename": source.filename,
                "page_number": (
                    source.page_number
                ),
                "chunk_index": (
                    source.chunk_index
                ),
                "similarity": (
                    source.similarity
                ),
                "distance": source.distance,
            }
            for source_number, source
            in enumerate(
                result.sources,
                start=1,
            )
        ]

        event = await (
            episodic_repository.record_event(
                user_id=payload.user_id,
                course_id=payload.course_id,
                session_id=(
                    payload.session_id
                ),
                event_type="summary.generated",
                entity_type="topic",
                payload={
                    "topic": payload.topic.strip(),
                    "summary": result.answer,
                    "generation_model": (
                        result.generation_model
                    ),
                    "preference_version": (
                        preferences.version
                    ),
                    "preferences_confirmed": (
                        preferences.confirmed
                    ),
                    "section_order": list(
                        preferences.section_order
                    ),
                    "sources": source_payload,
                },
            )
        )
    except ValueError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(error),
        ) from error
    except SummaryPreferenceError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
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
        for source_number, source
        in enumerate(
            result.sources,
            start=1,
        )
    ]

    return TopicSummaryResponse(
        summary_id=event.event_id,
        topic=payload.topic.strip(),
        summary=result.answer,
        generation_model=(
            result.generation_model
        ),
        preference_version=(
            preferences.version
        ),
        preferences_confirmed=(
            preferences.confirmed
        ),
        section_order=list(
            preferences.section_order
        ),
        sources=sources,
        created_at=event.occurred_at,
    )

@router.post(
    "/actions/notion/prepare",
    response_model=(
        PendingNotionActionResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
)
async def prepare_notion_publish(
    payload: NotionPublishPrepareRequest,
    request: Request,
) -> PendingNotionActionResponse:
    episodic_repository = (
        get_episodic_memory_repository(
            request
        )
    )
    action_repository = (
        get_pending_notion_action_repository(
            request
        )
    )

    try:
        summary_event = await (
            episodic_repository.get_event(
                user_id=payload.user_id,
                course_id=payload.course_id,
                event_id=payload.summary_id,
            )
        )

        if (
            summary_event.event_type
            != "summary.generated"
        ):
            raise ValueError(
                "The selected event is not a "
                "generated summary"
            )

        if (
            summary_event.session_id
            != payload.session_id
        ):
            raise ValueError(
                "Summary belongs to a different "
                "conversation"
            )

        topic = summary_event.payload.get(
            "topic"
        )
        summary = summary_event.payload.get(
            "summary"
        )

        if (
            not isinstance(topic, str)
            or not topic.strip()
            or not isinstance(summary, str)
            or not summary.strip()
        ):
            raise ValueError(
                "Stored summary contains invalid "
                "content"
            )

        title = (
            f"{topic.strip()} — "
            "StudyOps Summary"
        )[:200]

        action = await (
            action_repository
            .create_publish_action(
                user_id=payload.user_id,
                course_id=payload.course_id,
                session_id=(
                    payload.session_id
                ),
                summary_id=(
                    payload.summary_id
                ),
                title=title,
            )
        )

        await episodic_repository.record_event(
            user_id=payload.user_id,
            course_id=payload.course_id,
            session_id=payload.session_id,
            event_type=(
                "notion.publish_prepared"
            ),
            entity_type="summary",
            entity_id=payload.summary_id,
            payload={
                "action_id": action.action_id,
                "summary_id": (
                    action.summary_id
                ),
                "title": action.title,
                "expires_at": (
                    action.expires_at
                ),
            },
        )
    except EpisodicEventNotFoundError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
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
    except PendingNotionActionError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(error),
        ) from error

    return pending_notion_action_response(
        action
    )

@router.post(
    "/actions/notion/{action_id}/confirm",
    response_model=(
        NotionPublishConfirmationResponse
    ),
)
async def confirm_notion_publish(
    action_id: ActionId,
    payload: ActionUserRequest,
    request: Request,
) -> NotionPublishConfirmationResponse:
    action_repository = (
        get_pending_notion_action_repository(
            request
        )
    )
    episodic_repository = (
        get_episodic_memory_repository(
            request
        )
    )
    notion_client = get_notion_client(
        request
    )

    try:
        current_action = await (
            action_repository.get_action(
                user_id=payload.user_id,
                action_id=action_id,
            )
        )

        if (
            current_action.status
            == NOTION_COMPLETED_STATUS
        ):
            return (
                NotionPublishConfirmationResponse(
                    status="completed",
                    already_completed=True,
                    action=(
                        pending_notion_action_response(
                            current_action
                        )
                    ),
                )
            )

        action = await (
            action_repository
            .get_confirmable_action(
                user_id=payload.user_id,
                action_id=action_id,
            )
        )

        summary_event = await (
            episodic_repository.get_event(
                user_id=action.user_id,
                course_id=action.course_id,
                event_id=action.summary_id,
            )
        )

        if (
            summary_event.event_type
            != "summary.generated"
        ):
            raise ValueError(
                "The action does not reference a "
                "generated summary"
            )

        if (
            summary_event.session_id
            != action.session_id
        ):
            raise ValueError(
                "Summary belongs to a different "
                "conversation"
            )

        summary = summary_event.payload.get(
            "summary"
        )

        if (
            not isinstance(summary, str)
            or not summary.strip()
        ):
            raise ValueError(
                "Stored summary contains invalid "
                "content"
            )

    except PendingNotionActionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except EpisodicEventNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except PendingNotionActionExpiredError as error:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(error),
        ) from error
    except PendingNotionActionStateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except PendingNotionActionError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(error),
        ) from error

    try:
        page = await (
            notion_client.create_markdown_page(
                title=action.title,
                markdown=summary,
            )
        )
    except (
        NotionNotConfiguredError,
        NotionApiError,
    ) as error:
        # Keep the action pending so a temporary
        # Notion failure can be retried.
        try:
            await action_repository.record_failure(
                user_id=action.user_id,
                action_id=action.action_id,
                error_message=str(error),
            )

            await episodic_repository.record_event(
                user_id=action.user_id,
                course_id=action.course_id,
                session_id=action.session_id,
                event_type=(
                    "notion.publish_failed"
                ),
                entity_type="summary",
                entity_id=action.summary_id,
                payload={
                    "action_id": (
                        action.action_id
                    ),
                    "summary_id": (
                        action.summary_id
                    ),
                    "error": str(error)[:500],
                },
            )
        except RuntimeError:
            # Preserve the original Notion error.
            pass

        response_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if isinstance(
                error,
                NotionNotConfiguredError,
            )
            else status.HTTP_502_BAD_GATEWAY
        )

        raise HTTPException(
            status_code=response_status,
            detail=str(error),
        ) from error

    try:
        await action_repository.mark_completed(
            user_id=action.user_id,
            action_id=action.action_id,
            notion_page_id=page.page_id,
            notion_page_url=page.url,
        )

        completed_action = await (
            action_repository.get_action(
                user_id=action.user_id,
                action_id=action.action_id,
            )
        )
    except PendingNotionActionError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "The Notion page was created, but "
                "StudyOps could not save its final "
                f"action state. Page: {page.url}"
            ),
        ) from error

    try:
        await episodic_repository.record_event(
            user_id=action.user_id,
            course_id=action.course_id,
            session_id=action.session_id,
            event_type=(
                "notion.publish_completed"
            ),
            entity_type="summary",
            entity_id=action.summary_id,
            payload={
                "action_id": action.action_id,
                "summary_id": (
                    action.summary_id
                ),
                "notion_page_id": (
                    page.page_id
                ),
                "notion_page_url": page.url,
                "title": page.title,
            },
        )
    except RuntimeError:
        # The page and action state are already
        # complete. Do not encourage a duplicate
        # publish because event logging failed.
        pass

    return NotionPublishConfirmationResponse(
        status="completed",
        already_completed=False,
        action=pending_notion_action_response(
            completed_action
        ),
    )

@router.post(
    "/actions/notion/{action_id}/cancel",
    response_model=(
        NotionPublishCancelResponse
    ),
)
async def cancel_notion_publish(
    action_id: ActionId,
    payload: ActionUserRequest,
    request: Request,
) -> NotionPublishCancelResponse:
    action_repository = (
        get_pending_notion_action_repository(
            request
        )
    )
    episodic_repository = (
        get_episodic_memory_repository(
            request
        )
    )

    try:
        action = await (
            action_repository.get_action(
                user_id=payload.user_id,
                action_id=action_id,
            )
        )

        if (
            action.status
            == NOTION_CANCELLED_STATUS
        ):
            return NotionPublishCancelResponse(
                status="cancelled",
                action_id=action.action_id,
            )

        await action_repository.cancel_action(
            user_id=payload.user_id,
            action_id=action_id,
        )
    except PendingNotionActionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except PendingNotionActionStateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except PendingNotionActionError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(error),
        ) from error

    try:
        await episodic_repository.record_event(
            user_id=action.user_id,
            course_id=action.course_id,
            session_id=action.session_id,
            event_type=(
                "notion.publish_cancelled"
            ),
            entity_type="summary",
            entity_id=action.summary_id,
            payload={
                "action_id": action.action_id,
                "summary_id": (
                    action.summary_id
                ),
            },
        )
    except RuntimeError:
        # The action is already cancelled, so an
        # event-log failure must not reverse it.
        pass

    return NotionPublishCancelResponse(
        status="cancelled",
        action_id=action.action_id,
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