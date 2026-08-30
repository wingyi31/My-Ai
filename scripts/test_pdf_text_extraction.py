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


load_dotenv()


async def main() -> None:
    if len(sys.argv) != 4:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_pdf_text_extraction "
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

    if (
        file_record.get("upload_status")
        != "uploaded"
    ):
        raise RuntimeError(
            "File has not been uploaded "
            "successfully"
        )

    storage_repository = (
        CloudStorageRepository(
            get_storage_bucket()
        )
    )

    if (
        file_record["storage_bucket"]
        != storage_repository.bucket.name
    ):
        raise RuntimeError(
            "Firestore bucket does not match "
            "the configured bucket"
        )

    pdf_content = (
        await storage_repository.download_object(
            file_record["storage_object"]
        )
    )

    extraction_service = (
        PdfExtractionService()
    )

    result = extraction_service.extract(
        pdf_content
    )

    print("PDF extraction successful")
    print("Filename:", file_record["filename"])
    print("Pages:", result.page_count)
    print(
        "Characters:",
        result.total_characters,
    )
    print("Needs OCR:", result.needs_ocr)

    first_page_with_text = next(
        (
            page
            for page in result.pages
            if page.text
        ),
        None,
    )

    if first_page_with_text:
        print()
        print(
            "Preview from page",
            first_page_with_text.page_number,
        )
        print(
            first_page_with_text.text[:500]
        )


if __name__ == "__main__":
    asyncio.run(main())