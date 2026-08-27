import asyncio
import sys

from dotenv import load_dotenv

from app.connectors.canvas.client import (
    CanvasReadOnlyClient,
)
from app.connectors.canvas.settings import (
    CanvasSettings,
)
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


load_dotenv()


async def main() -> None:
    if len(sys.argv) != 5:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_canvas_file_upload "
            "<user_id> <course_id> "
            "<file_id> <source_key>"
        )

    canvas_user_id = sys.argv[1]
    course_id = sys.argv[2]
    file_id = sys.argv[3]
    source_key = sys.argv[4]

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

    if not source_key.strip():
        raise RuntimeError(
            "source_key must not be empty"
        )

    settings = CanvasSettings()

    metadata_path = (
        f"courses/{course_id}/files/{file_id}"
    )

    metadata_url = (
        f"{str(settings.base_url).rstrip('/')}/"
        f"api/v1/{metadata_path}"
    )

    async with CanvasReadOnlyClient(
        base_url=settings.base_url,
        access_token=(
            settings.access_token.get_secret_value()
        ),
    ) as canvas:
        downloaded_file = (
            await canvas.download_file(
                metadata_path
            )
        )

    storage_repository = CloudStorageRepository(
        get_storage_bucket()
    )

    stored_object = (
        await storage_repository.upload_canvas_file(
            user_id=canvas_user_id,
            course_id=course_id,
            downloaded_file=downloaded_file,
        )
    )

    firestore_repository = (
        CanvasFirestoreRepository(
            get_firestore_client()
        )
    )

    await firestore_repository.persist_file_upload(
        user_id=canvas_user_id,
        course_id=course_id,
        source_key=source_key,
        canvas_file_id=(
            downloaded_file.canvas_file_id
        ),
        metadata_url=metadata_url,
        filename=downloaded_file.filename,
        content_type=(
            downloaded_file.content_type
        ),
        size_bytes=stored_object.size_bytes,
        sha256=stored_object.sha256,
        storage_bucket=(
            stored_object.bucket_name
        ),
        storage_object=(
            stored_object.object_name
        ),
    )

    print("Canvas file processing successful")
    print("Filename:", downloaded_file.filename)
    print("Bytes:", stored_object.size_bytes)
    print(
        "Storage:",
        (
            f"gs://{stored_object.bucket_name}/"
            f"{stored_object.object_name}"
        ),
    )
    print(
        "New upload:",
        stored_object.uploaded,
    )
    print("Firestore status: uploaded")


if __name__ == "__main__":
    asyncio.run(main())