import asyncio
from typing import Any

from app.services.canvas_sync_orchestrator import (
    CanvasSyncOrchestrator,
)


class FakeRepository:

    def __init__(
        self,
        *,
        files: list[dict[str, Any]],
        chunks: dict[
            str,
            list[dict[str, Any]],
        ],
    ) -> None:
        self.files = files
        self.chunks = chunks
        self.persisted_embeddings: list[
            dict[str, Any]
        ] = []

    async def list_course_files(
        self,
        *,
        user_id: str,
        course_id: str,
        uploaded_only: bool = True,
    ) -> list[dict[str, Any]]:
        return self.files

    async def list_file_chunks(
        self,
        *,
        user_id: str,
        course_id: str,
        canvas_file_id: str,
    ) -> list[dict[str, Any]]:
        return self.chunks.get(
            canvas_file_id,
            [],
        )

    async def persist_chunk_embedding(
        self,
        *,
        user_id: str,
        course_id: str,
        canvas_file_id: str,
        chunk_id: str,
        embedding: list[float],
        embedding_model: str,
        text_hash: str,
    ) -> None:
        self.persisted_embeddings.append(
            {
                "canvas_file_id": (
                    canvas_file_id
                ),
                "chunk_id": chunk_id,
                "embedding": embedding,
                "embedding_model": (
                    embedding_model
                ),
                "text_hash": text_hash,
            }
        )


class FakePdfProcessingService:

    def __init__(
        self,
        outcomes: dict[
            str,
            dict[str, Any] | Exception,
        ],
    ) -> None:
        self.outcomes = outcomes
        self.processed_file_ids: list[
            str
        ] = []

    async def process_file(
        self,
        *,
        user_id: str,
        course_id: str,
        canvas_file_id: str,
    ) -> dict[str, Any]:
        self.processed_file_ids.append(
            canvas_file_id
        )

        outcome = self.outcomes[
            canvas_file_id
        ]

        if isinstance(
            outcome,
            Exception,
        ):
            raise outcome

        return outcome


class FakeEmbeddingService:

    model = "test-embedding-model"
    dimensions = 3

    def __init__(self) -> None:
        self.requests: list[
            list[str]
        ] = []

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        self.requests.append(texts)

        return [
            [0.1, 0.2, 0.3]
            for _ in texts
        ]


async def fake_ingestion_runner(
    *,
    canvas_user_id: str,
    course_id: str,
) -> dict[str, int]:
    return {
        "total": 1,
        "new": 0,
        "changed": 0,
        "unchanged": 1,
    }


def test_sync_skips_current_embeddings() -> None:
    async def run() -> None:
        repository = FakeRepository(
            files=[
                {
                    "canvas_file_id": "101",
                    "filename": "lecture.pdf",
                    "content_type": (
                        "application/pdf"
                    ),
                    "upload_status": (
                        "uploaded"
                    ),
                },
                {
                    "canvas_file_id": "102",
                    "filename": "notes.txt",
                    "content_type": (
                        "text/plain"
                    ),
                    "upload_status": (
                        "uploaded"
                    ),
                },
            ],
            chunks={
                "101": [
                    {
                        "chunk_id": (
                            "p0001-c0000"
                        ),
                        "text": "Current text",
                        "text_hash": "hash-1",
                        "embedding": [
                            0.1,
                            0.2,
                            0.3,
                        ],
                        "embedding_text_hash": (
                            "hash-1"
                        ),
                        "embedding_model": (
                            "test-embedding-model"
                        ),
                        "embedding_dimensions": 3,
                    }
                ]
            },
        )

        pdf_service = (
            FakePdfProcessingService(
                {
                    "101": {
                        "status": "current",
                        "chunk_count": 1,
                    }
                }
            )
        )

        embedding_service = (
            FakeEmbeddingService()
        )

        orchestrator = (
            CanvasSyncOrchestrator(
                repository=repository,
                pdf_processing_service=(
                    pdf_service
                ),
                embedding_service=(
                    embedding_service
                ),
                ingestion_runner=(
                    fake_ingestion_runner
                ),
            )
        )

        result = await orchestrator.sync(
            canvas_user_id="123",
            course_id="96996",
        )

        assert result["pdf_files"] == 1
        assert result["non_pdf_files"] == 1
        assert result["pdf_current"] == 1
        assert result["pdf_processed"] == 0
        assert (
            result["chunks_embedded"]
            == 0
        )
        assert (
            result["chunks_skipped"]
            == 1
        )
        assert (
            result[
                "pdf_processing_failed"
            ]
            == 0
        )
        assert (
            result["embedding_failed"]
            == 0
        )
        assert result["failures"] == []
        assert embedding_service.requests == []
        assert (
            repository
            .persisted_embeddings
            == []
        )

    asyncio.run(run())


def test_sync_continues_after_pdf_failure() -> None:
    async def run() -> None:
        repository = FakeRepository(
            files=[
                {
                    "canvas_file_id": "201",
                    "filename": "broken.pdf",
                    "content_type": (
                        "application/pdf"
                    ),
                    "upload_status": (
                        "uploaded"
                    ),
                },
                {
                    "canvas_file_id": "202",
                    "filename": "working.pdf",
                    "content_type": (
                        "application/pdf"
                    ),
                    "upload_status": (
                        "uploaded"
                    ),
                },
            ],
            chunks={
                "202": [
                    {
                        "chunk_id": (
                            "p0001-c0000"
                        ),
                        "text": (
                            "Searchable content"
                        ),
                        "text_hash": "hash-2",
                    }
                ]
            },
        )

        pdf_service = (
            FakePdfProcessingService(
                {
                    "201": RuntimeError(
                        "Invalid PDF"
                    ),
                    "202": {
                        "status": "processed",
                        "chunk_count": 1,
                    },
                }
            )
        )

        embedding_service = (
            FakeEmbeddingService()
        )

        orchestrator = (
            CanvasSyncOrchestrator(
                repository=repository,
                pdf_processing_service=(
                    pdf_service
                ),
                embedding_service=(
                    embedding_service
                ),
                ingestion_runner=(
                    fake_ingestion_runner
                ),
            )
        )

        result = await orchestrator.sync(
            canvas_user_id="123",
            course_id="96996",
        )

        assert result["pdf_files"] == 2
        assert result["pdf_processed"] == 1
        assert (
            result[
                "pdf_processing_failed"
            ]
            == 1
        )
        assert (
            result["embedding_failed"]
            == 0
        )
        assert (
            result["chunks_embedded"]
            == 1
        )

        assert len(
            result["failures"]
        ) == 1
        assert (
            result["failures"][0][
                "canvas_file_id"
            ]
            == "201"
        )
        assert (
            result["failures"][0][
                "stage"
            ]
            == "pdf_processing"
        )

        assert len(
            repository
            .persisted_embeddings
        ) == 1
        assert (
            repository
            .persisted_embeddings[0][
                "canvas_file_id"
            ]
            == "202"
        )

    asyncio.run(run())