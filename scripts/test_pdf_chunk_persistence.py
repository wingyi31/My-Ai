import asyncio
import sys

from dotenv import load_dotenv

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
from app.services.pdf_extraction_service import (
    PdfExtractionService,
)
from app.services.text_chunking_service import (
    TextChunkingService,
)


load_dotenv()


async def main() -> None:
    if len(sys.argv) != 4:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_pdf_chunk_persistence "
            "<user_id> <course_id> <file_id>"
        )

    canvas_user_id = sys.argv[1]
    course_id = sys.argv[2]
    file_id = sys.argv[3]

    if not canvas_user_id.isdecimal():
        raise RuntimeError(
            "user_id must contain digits only"
        )

    if not course_id.isdecimal():
        raise RuntimeError(
            "course_id must contain digits only"
        )

    if not file_id.isdecimal():
        raise RuntimeError(
            "file_id must contain digits only"
        )

    firestore_repository = (
        CanvasFirestoreRepository(
            get_firestore_client()
        )
    )

    file_record = (
        await firestore_repository
        .get_file_record(
            user_id=canvas_user_id,
            course_id=course_id,
            canvas_file_id=file_id,
        )
    )

    if file_record is None:
        raise RuntimeError(
            "Firestore file record not found"
        )

    file_sha256 = file_record["sha256"]

    if (
        file_record.get(
            "extraction_status"
        )
        == "complete"
        and file_record.get(
            "extraction_sha256"
        )
        == file_sha256
    ):
        print(
            "PDF extraction is already current"
        )
        print(
            "Chunks:",
            file_record.get("chunk_count", 0),
        )
        return

    storage_repository = (
        CloudStorageRepository(
            get_storage_bucket()
        )
    )

    pdf_content = (
        await storage_repository.download_object(
            file_record["storage_object"]
        )
    )

    extraction = (
        PdfExtractionService().extract(
            pdf_content
        )
    )

    if extraction.needs_ocr:
        raise RuntimeError(
            "PDF requires OCR before chunking"
        )

    chunks = TextChunkingService().chunk(
        extraction
    )

    if not chunks:
        raise RuntimeError(
            "PDF produced no searchable chunks"
        )

    await (
        firestore_repository
        .replace_file_chunks(
            user_id=canvas_user_id,
            course_id=course_id,
            canvas_file_id=file_id,
            filename=file_record["filename"],
            file_sha256=file_sha256,
            page_count=(
                extraction.page_count
            ),
            total_characters=(
                extraction.total_characters
            ),
            chunks=chunks,
        )
    )

    print("PDF chunks persisted")
    print("Filename:", file_record["filename"])
    print("Pages:", extraction.page_count)
    print(
        "Characters:",
        extraction.total_characters,
    )
    print("Chunks:", len(chunks))

    print()
    print("First chunk preview:")
    print(chunks[0].text[:500])


if __name__ == "__main__":
    asyncio.run(main())