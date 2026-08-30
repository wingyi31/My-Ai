from __future__ import annotations

from typing import Any

from app.repositories.cloud_storage_repository import (
    CloudStorageRepository,
)
from app.repositories.firestore_repository import (
    CanvasFirestoreRepository,
)
from app.services.pdf_extraction_service import (
    PdfExtractionService,
)
from app.services.text_chunking_service import (
    TextChunkingService,
)


def is_pdf_record(
    record: dict[str, Any],
) -> bool:
    content_type = str(
        record.get("content_type") or ""
    ).split(";", 1)[0].strip().lower()

    filename = str(
        record.get("filename") or ""
    ).lower()

    return (
        content_type == "application/pdf"
        or filename.endswith(".pdf")
    )


class PdfProcessingService:

    def __init__(
        self,
        *,
        repository: CanvasFirestoreRepository,
        storage_repository: (
            CloudStorageRepository
        ),
        extraction_service: (
            PdfExtractionService | None
        ) = None,
        chunking_service: (
            TextChunkingService | None
        ) = None,
    ) -> None:
        self._repository = repository
        self._storage_repository = (
            storage_repository
        )
        self._extraction_service = (
            extraction_service
            or PdfExtractionService()
        )
        self._chunking_service = (
            chunking_service
            or TextChunkingService()
        )

    async def process_file(
        self,
        *,
        user_id: str,
        course_id: str,
        canvas_file_id: str,
    ) -> dict[str, Any]:
        record = (
            await self._repository
            .get_file_record(
                user_id=user_id,
                course_id=course_id,
                canvas_file_id=(
                    canvas_file_id
                ),
            )
        )

        if record is None:
            raise RuntimeError(
                "Firestore file record not found"
            )

        if (
            record.get("upload_status")
            != "uploaded"
        ):
            return {
                "status": "not_uploaded",
                "chunk_count": 0,
            }

        if not is_pdf_record(record):
            return {
                "status": "not_pdf",
                "chunk_count": 0,
            }

        file_sha256 = str(
            record.get("sha256") or ""
        )

        if not file_sha256:
            raise RuntimeError(
                "Uploaded file has no SHA-256"
            )

        if (
            record.get("extraction_status")
            == "complete"
            and record.get(
                "extraction_sha256"
            )
            == file_sha256
        ):
            return {
                "status": "current",
                "chunk_count": int(
                    record.get(
                        "chunk_count",
                        0,
                    )
                ),
            }

        storage_object = str(
            record.get("storage_object")
            or ""
        )

        if not storage_object:
            raise RuntimeError(
                "Uploaded file has no "
                "storage object"
            )

        pdf_content = await (
            self._storage_repository
            .download_object(
                storage_object
            )
        )

        extraction = (
            self._extraction_service
            .extract(pdf_content)
        )

        if extraction.needs_ocr:
            raise RuntimeError(
                "PDF requires OCR before "
                "chunking"
            )

        chunks = (
            self._chunking_service
            .chunk(extraction)
        )

        if not chunks:
            raise RuntimeError(
                "PDF produced no searchable "
                "chunks"
            )

        filename = str(
            record.get("filename")
            or canvas_file_id
        )

        await self._repository.replace_file_chunks(
            user_id=user_id,
            course_id=course_id,
            canvas_file_id=canvas_file_id,
            filename=filename,
            file_sha256=file_sha256,
            page_count=extraction.page_count,
            total_characters=(
                extraction.total_characters
            ),
            chunks=chunks,
        )

        return {
            "status": "processed",
            "page_count": (
                extraction.page_count
            ),
            "character_count": (
                extraction.total_characters
            ),
            "chunk_count": len(chunks),
        }