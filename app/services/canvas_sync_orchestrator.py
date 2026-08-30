from __future__ import annotations

import logging
from uuid import uuid4

logger = logging.getLogger(__name__)


class CanvasSyncAlreadyRunningError(
    RuntimeError
):
    pass

from collections.abc import (
    Awaitable,
    Callable,
)
from typing import Any

from app.core.config import get_settings
from app.repositories.cloud_storage_repository import (
    CloudStorageRepository,
)
from app.repositories.firestore_client import (
    get_firestore_client,
)
from app.repositories.firestore_repository import (
    CanvasFirestoreRepository,
)
from app.repositories.storage_client import (
    get_storage_bucket,
)
from app.services.canvas_ingestion_service import (
    run_canvas_ingestion,
)
from app.services.chunk_embedding_service import (
    embed_file_chunks,
)
from app.services.embedding_service import (
    VertexEmbeddingService,
)
from app.services.pdf_processing_service import (
    PdfProcessingService,
    is_pdf_record,
)


IngestionRunner = Callable[
    ...,
    Awaitable[dict[str, int]],
]


class CanvasSyncOrchestrator:

    def __init__(
        self,
        *,
        repository: CanvasFirestoreRepository,
        pdf_processing_service: (
            PdfProcessingService
        ),
        embedding_service: (
            VertexEmbeddingService
        ),
        ingestion_runner: IngestionRunner = (
            run_canvas_ingestion
        ),
    ) -> None:
        self._repository = repository
        self._pdf_processing_service = (
            pdf_processing_service
        )
        self._embedding_service = (
            embedding_service
        )
        self._ingestion_runner = (
            ingestion_runner
        )

    async def sync(
        self,
        *,
        canvas_user_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        ingestion_stats = await (
            self._ingestion_runner(
                canvas_user_id=canvas_user_id,
                course_id=course_id,
            )
        )

        file_records = await (
            self._repository
            .list_course_files(
                user_id=canvas_user_id,
                course_id=course_id,
                uploaded_only=True,
            )
        )

        result: dict[str, Any] = {
            "ingestion": ingestion_stats,
            "uploaded_files": len(
                file_records
            ),
            "pdf_files": 0,
            "non_pdf_files": 0,
            "pdf_processed": 0,
            "pdf_current": 0,
            "pdf_processing_failed": 0,
            "embedding_failed": 0,
            "total_chunks": 0,
            "chunks_embedded": 0,
            "chunks_skipped": 0,
            "empty_chunks": 0,
            "failures": [],
        }

        for record in file_records:
            if not is_pdf_record(record):
                result["non_pdf_files"] += 1
                continue

            result["pdf_files"] += 1

            file_id = str(
                record["canvas_file_id"]
            )

            try:
                processing = await (
                    self._pdf_processing_service
                    .process_file(
                        user_id=(
                            canvas_user_id
                        ),
                        course_id=course_id,
                        canvas_file_id=file_id,
                    )
                )
            except Exception as exc:
                result[
                    "pdf_processing_failed"
                ] += 1

                result["failures"].append(
                    {
                        "canvas_file_id": (
                            file_id
                        ),
                        "stage": (
                            "pdf_processing"
                        ),
                        "error_type": (
                            type(exc).__name__
                        ),
                        "message": str(exc),
                    }
                )
                continue

            status = str(
                processing.get("status")
                or ""
            )

            if status == "processed":
                result["pdf_processed"] += 1
            elif status == "current":
                result["pdf_current"] += 1
            else:
                continue

            try:
                embedding = await (
                    embed_file_chunks(
                        user_id=(
                            canvas_user_id
                        ),
                        course_id=course_id,
                        canvas_file_id=file_id,
                        repository=(
                            self._repository
                        ),
                        embedding_service=(
                            self
                            ._embedding_service
                        ),
                    )
                )
            except Exception as exc:
                result[
                    "embedding_failed"
                ] += 1

                result["failures"].append(
                    {
                        "canvas_file_id": (
                            file_id
                        ),
                        "stage": "embedding",
                        "error_type": (
                            type(exc).__name__
                        ),
                        "message": str(exc),
                    }
                )
                continue

            result["total_chunks"] += (
                embedding["total_chunks"]
            )
            result["chunks_embedded"] += (
                embedding["embedded"]
            )
            result["chunks_skipped"] += (
                embedding["skipped"]
            )
            result["empty_chunks"] += (
                embedding["empty"]
            )

        return result


async def run_canvas_sync(
    *,
    canvas_user_id: str,
    course_id: str,
) -> dict[str, Any]:
    if not canvas_user_id.isdecimal():
        raise ValueError(
            "canvas_user_id must contain "
            "digits only"
        )

    if not course_id.isdecimal():
        raise ValueError(
            "course_id must contain "
            "digits only"
        )

    settings = get_settings()

    repository = CanvasFirestoreRepository(
        get_firestore_client()
    )

    lease_owner_id = uuid4().hex

    lease_acquired = await (
        repository
        .acquire_course_sync_lease(
            user_id=canvas_user_id,
            course_id=course_id,
            owner_id=lease_owner_id,
            lease_seconds=(
                settings
                .canvas_sync_lease_seconds
            ),
        )
    )

    if not lease_acquired:
        raise (
            CanvasSyncAlreadyRunningError(
                "Canvas synchronization is "
                "already running for "
                f"user {canvas_user_id}, "
                f"course {course_id}"
            )
        )

    try:
        storage_repository = (
            CloudStorageRepository(
                get_storage_bucket()
            )
        )

        pdf_processing_service = (
            PdfProcessingService(
                repository=repository,
                storage_repository=(
                    storage_repository
                ),
            )
        )

        async with VertexEmbeddingService(
            project_id=(
                settings.google_cloud_project
            ),
            location=(
                settings
                .google_cloud_location
            ),
            model=(
                settings.embedding_model
            ),
            dimensions=(
                settings.embedding_dimension
            ),
        ) as embedding_service:
            orchestrator = (
                CanvasSyncOrchestrator(
                    repository=repository,
                    pdf_processing_service=(
                        pdf_processing_service
                    ),
                    embedding_service=(
                        embedding_service
                    ),
                )
            )

            return await orchestrator.sync(
                canvas_user_id=(
                    canvas_user_id
                ),
                course_id=course_id,
            )

    finally:
        try:
            released = await (
                repository
                .release_course_sync_lease(
                    user_id=canvas_user_id,
                    course_id=course_id,
                    owner_id=(
                        lease_owner_id
                    ),
                )
            )

            if not released:
                logger.warning(
                    "Canvas synchronization "
                    "lease was not released "
                    "because ownership changed"
                )

        except Exception:
            # The lease expires automatically,
            # so a release failure must not hide
            # the original sync result/error.
            logger.exception(
                "Failed to release Canvas "
                "synchronization lease"
            )