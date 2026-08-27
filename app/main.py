from contextlib import asynccontextmanager

from pathlib import Path

from fastapi.staticfiles import StaticFiles

import httpx
from fastapi import FastAPI
from google.cloud import tasks_v2

from app.connectors.canvas import CanvasClient
from app.connectors.gmail.client import (
    GmailClient,
)
from app.connectors.gmail.oauth import (
    GmailCredentialStore,
    GmailOAuthClient,
    OAuthStateSigner,
)
from app.connectors.gmail.service import (
    GmailService,
)
from app.connectors.moodle import MoodleClient
from app.core.config import get_settings
from app.jobs.gmail_sync import (
    GmailSyncJob,
    JsonGmailSyncStateStore,
)
from app.repositories.firestore_client import (
    get_firestore_client,
)
from app.routes.ui import (
    router as ui_router,
)
from app.routes.agent import (
    router as agent_router,
)
from app.routes.canvas import (
    router as canvas_router,
)
from app.routes.canvas_scheduler import (
    router as canvas_scheduler_router,
)
from app.routes.canvas_sync import (
    router as canvas_sync_router,
)
from app.routes.gmail import (
    router as gmail_router,
)
from app.routes.health import (
    router as health_router,
)
from app.routes.mytimes import (
    router as mytimes_router,
)
from app.routes.rag import (
    router as rag_router,
)
from app.services.academic_agent_service import (
    AcademicAgentService,
)
from app.services.canvas_task_service import (
    CanvasSyncTaskEnqueuer,
)
from app.services.embedding_service import (
    VertexEmbeddingService,
)
from app.services.rag_answer_service import (
    RagAnswerService,
)
from app.services.semantic_search_service import (
    SemanticSearchService,
)
from app.services.canvas_reader import (
    CanvasReadService,
)
from app.workers.email_processor import (
    EmailProcessor,
)

from app.connectors.calendar import (
    GoogleCalendarClient,
)
from app.repositories.pending_action_repository import (
    PendingActionRepository,
)
from app.services.calendar_action_service import (
    CalendarActionService,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Create shared clients once for the lifetime
    of the Cloud Run instance.
    """
    settings = get_settings()

    cloud_tasks_client = (
        tasks_v2.CloudTasksAsyncClient()
    )

    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            settings
            .moodle_request_timeout_seconds
        ),
        follow_redirects=False,
        trust_env=settings.http_trust_env,
    )

    gmail_http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            settings
            .gmail_request_timeout_seconds
        ),
        follow_redirects=False,
        trust_env=settings.http_trust_env,
    )

    canvas_http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            settings
            .canvas_request_timeout_seconds
        ),
        follow_redirects=False,
        trust_env=settings.http_trust_env,
    )

    app.state.moodle_client = MoodleClient(
        http_client=http_client,
        base_url=settings.mytimes_base_url,
        token=(
            settings
            .mytimes_token
            .get_secret_value()
            if settings.mytimes_token
            else None
        ),
    )

    app.state.canvas_client = CanvasClient(
        http_client=canvas_http_client,
        base_url=settings.canvas_base_url,
        access_token=(
            settings
            .canvas_access_token
            .get_secret_value()
            if settings.canvas_access_token
            else None
        ),
    )
    canvas_read_service = CanvasReadService(
        app.state.canvas_client
    )

    app.state.canvas_read_service = (
        canvas_read_service
    )
    

    gmail_credential_store = (
        GmailCredentialStore(
            configured_refresh_token=(
                settings
                .gmail_refresh_token
                .get_secret_value()
                if settings.gmail_refresh_token
                else None
            ),
            path=settings.gmail_token_path,
        )
    )

    gmail_oauth_client = GmailOAuthClient(
        http_client=gmail_http_client,
        client_id=(
            settings
            .gmail_client_id
            .get_secret_value()
            if settings.gmail_client_id
            else None
        ),
        client_secret=(
            settings
            .gmail_client_secret
            .get_secret_value()
            if settings.gmail_client_secret
            else None
        ),
        redirect_uri=(
            settings.gmail_redirect_uri
        ),
        state_signer=OAuthStateSigner(
            settings
            .gmail_oauth_state_secret
            .get_secret_value()
            if settings
            .gmail_oauth_state_secret
            else None
        ),
    )

    gmail_client = GmailClient(
        http_client=gmail_http_client,
        oauth_client=gmail_oauth_client,
        credential_store=(
            gmail_credential_store
        ),
    )
    calendar_client = GoogleCalendarClient(
        http_client=gmail_http_client,
        oauth_client=gmail_oauth_client,
        credential_store=(
            gmail_credential_store
        ),
    )

    app.state.calendar_client = (
        calendar_client
    )

    gmail_service = GmailService(
        gmail_client,
        EmailProcessor(),
    )

    app.state.gmail_credential_store = (
        gmail_credential_store
    )
    app.state.gmail_oauth_client = (
        gmail_oauth_client
    )
    app.state.gmail_client = gmail_client
    app.state.gmail_sync_job = GmailSyncJob(
        service=gmail_service,
        state_store=JsonGmailSyncStateStore(
            settings.gmail_sync_state_path
        ),
        query=settings.gmail_sync_query,
        max_messages=(
            settings
            .gmail_max_messages_per_sync
        ),
    )

    firestore_client = (
        get_firestore_client()
    )
    pending_action_repository = (
        PendingActionRepository(
            firestore_client
        )
    )

    calendar_action_service = (
        CalendarActionService(
            canvas_read_service=(
                canvas_read_service
            ),
            calendar_client=(
                calendar_client
            ),
            action_repository=(
                pending_action_repository
            ),
        )
    )

    app.state.pending_action_repository = (
        pending_action_repository
    )
    app.state.calendar_action_service = (
        calendar_action_service
    )

    embedding_service = (
        VertexEmbeddingService(
            project_id=(
                settings.google_cloud_project
            ),
            location=(
                settings.google_cloud_location
            ),
            model=settings.embedding_model,
            dimensions=(
                settings.embedding_dimension
            ),
        )
    )

    semantic_search_service = (
        SemanticSearchService(
            db=firestore_client,
            embedding_service=(
                embedding_service
            ),
        )
    )

    rag_answer_service = RagAnswerService(
        project_id=(
            settings.google_cloud_project
        ),
        location=(
            settings.google_cloud_location
        ),
        generation_model=(
            settings.generation_model
        ),
        search_service=(
            semantic_search_service
        ),
        min_similarity=(
            settings.rag_min_similarity
        ),
    )

    academic_agent_service = (
        AcademicAgentService(
            project_id=(
                settings.google_cloud_project
            ),
            location=(
                settings.google_cloud_location
            ),
            generation_model=(
                settings.generation_model
            ),
            rag_answer_service=(
                rag_answer_service
            ),
            canvas_read_service=(
                canvas_read_service
            ),
            default_source_limit=(
                settings.rag_default_source_limit
            ),
            calendar_action_service=(
                calendar_action_service
            ),
        )
    )

    app.state.embedding_service = (
        embedding_service
    )
    app.state.semantic_search_service = (
        semantic_search_service
    )
    app.state.rag_answer_service = (
        rag_answer_service
    )
    app.state.academic_agent_service = (
        academic_agent_service
    )

    app.state.canvas_task_enqueuer = (
        CanvasSyncTaskEnqueuer(
            client=cloud_tasks_client,
            project_id=(
                settings.google_cloud_project
            ),
            location=(
                settings
                .cloud_tasks_location
            ),
            queue_name=(
                settings.cloud_tasks_queue
            ),
            worker_base_url=(
                settings
                .cloud_tasks_worker_base_url
            ),
            service_account_email=(
                settings
                .cloud_tasks_service_account_email
            ),
            dispatch_deadline_seconds=(
                settings
                .cloud_tasks_dispatch_deadline_seconds
            ),
        )
    )

    try:
        yield
    finally:
        await academic_agent_service.close()
        await rag_answer_service.close()
        await embedding_service.close()
        await http_client.aclose()
        await gmail_http_client.aclose()
        await canvas_http_client.aclose()
        await (
            cloud_tasks_client
            .transport
            .close()
        )


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
static_directory = (
    Path(__file__).resolve().parent
    / "static"
)

app.mount(
    "/static",
    StaticFiles(
        directory=static_directory
    ),
    name="static",
)

app.include_router(ui_router)
app.include_router(health_router)
app.include_router(canvas_router)
app.include_router(canvas_sync_router)
app.include_router(gmail_router)
app.include_router(mytimes_router)
app.include_router(rag_router)
app.include_router(agent_router)
app.include_router(canvas_scheduler_router)