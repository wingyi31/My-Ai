from app.connectors.canvas.client import (
    CanvasReadOnlyClient,
)
from app.connectors.canvas.course_scanner import (
    CanvasCourseScanner,
)
from app.connectors.canvas.discovery import (
    CanvasDiscoveryService,
)
from app.connectors.canvas.normalizer import (
    normalize_assignment,
    normalize_page,
)
from app.connectors.canvas.settings import (
    CanvasSettings,
)
from app.connectors.canvas.deduplicator import (
    decide_change,
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


async def run_canvas_ingestion(
    *,
    canvas_user_id: str,
    course_id: str,
) -> dict[str, int]:
    settings = CanvasSettings()

    firestore_repository = (
        CanvasFirestoreRepository(
            get_firestore_client()
        )
    )

    storage_repository = (
        CloudStorageRepository(
            get_storage_bucket()
        )
    )

    async with CanvasReadOnlyClient(
        base_url=settings.base_url,
        access_token=(
            settings.access_token.get_secret_value()
        ),
    ) as canvas:
        discovery = CanvasDiscoveryService(canvas)

        scanner = CanvasCourseScanner(
            discovery=discovery,
            base_url=str(settings.base_url),
        )

        pages = await scanner.scan_pages(course_id)

        assignments = (
            await discovery.list_assignments(
                course_id
            )
        )

        normalized_pages = [
            normalize_page(page)
            for page in pages
        ]

        normalized_assignments = [
            normalize_assignment(
                assignment=assignment,
                course_id=course_id,
                canvas_base_url=str(
                    settings.base_url
                ),
            )
            for assignment in assignments
        ]

        normalized_items = (
            normalized_pages
            + normalized_assignments
        )

        await firestore_repository.mark_course_synced(
            user_id=canvas_user_id,
            course_id=course_id,
        )

        stats = {
            "total": len(normalized_items),
            "new": 0,
            "changed": 0,
            "unchanged": 0,
            "written": 0,
            "file_references_seen": 0,
            "unique_files_processed": 0,
            "files_uploaded": 0,
            "files_reused": 0,
            "file_links_recorded": 0,
            "files_failed": 0,
        }

        # Persist normalized pages and assignments.
        for item in normalized_items:
            existing_hash = (
                await firestore_repository
                .get_revision_hash(
                    user_id=canvas_user_id,
                    course_id=course_id,
                    source_key=item.source_key,
                )
            )

            decision = decide_change(
                item=item,
                existing_revision_hash=(
                    existing_hash
                ),
            )

            change_type = (
                decision.change_type.value
            )

            if change_type not in stats:
                stats[change_type] = 0

            stats[change_type] += 1

            if change_type != "unchanged":
                await firestore_repository.persist_item(
                    user_id=canvas_user_id,
                    course_id=course_id,
                    item=item,
                    revision_hash=(
                        decision.revision_hash
                    ),
                )

                stats["written"] += 1

        # Prevent downloading the same Canvas file
        # multiple times during one synchronization.
        processed_files = {}
        failed_files: dict[str, str] = {}

        for item in normalized_items:
            for reference in item.file_references:
                stats["file_references_seen"] += 1

                file_id = str(
                    reference.canvas_file_id
                )

                metadata_url = str(reference.url)

                if file_id in failed_files:
                    await (
                        firestore_repository
                        .persist_file_failure(
                            user_id=canvas_user_id,
                            course_id=course_id,
                            source_key=(
                                item.source_key
                            ),
                            canvas_file_id=file_id,
                            metadata_url=metadata_url,
                            error_type=(
                                failed_files[file_id]
                            ),
                        )
                    )
                    continue

                try:
                    if file_id not in processed_files:
                        metadata_path = (
                            f"courses/{course_id}/"
                            f"files/{file_id}"
                        )

                        downloaded_file = (
                            await canvas.download_file(
                                metadata_path
                            )
                        )

                        stored_object = (
                            await storage_repository
                            .upload_canvas_file(
                                user_id=(
                                    canvas_user_id
                                ),
                                course_id=course_id,
                                downloaded_file=(
                                    downloaded_file
                                ),
                            )
                        )

                        processed_files[file_id] = (
                            downloaded_file,
                            stored_object,
                        )

                        stats[
                            "unique_files_processed"
                        ] += 1

                        if stored_object.uploaded:
                            stats[
                                "files_uploaded"
                            ] += 1
                        else:
                            stats[
                                "files_reused"
                            ] += 1

                    else:
                        (
                            downloaded_file,
                            stored_object,
                        ) = processed_files[file_id]

                    await (
                        firestore_repository
                        .persist_file_upload(
                            user_id=canvas_user_id,
                            course_id=course_id,
                            source_key=(
                                item.source_key
                            ),
                            canvas_file_id=file_id,
                            metadata_url=metadata_url,
                            filename=(
                                downloaded_file.filename
                            ),
                            content_type=(
                                downloaded_file
                                .content_type
                            ),
                            size_bytes=(
                                stored_object
                                .size_bytes
                            ),
                            sha256=(
                                stored_object.sha256
                            ),
                            storage_bucket=(
                                stored_object
                                .bucket_name
                            ),
                            storage_object=(
                                stored_object
                                .object_name
                            ),
                        )
                    )

                    stats[
                        "file_links_recorded"
                    ] += 1

                except Exception as exc:
                    error_type = type(exc).__name__

                    if file_id not in failed_files:
                        failed_files[file_id] = (
                            error_type
                        )
                        stats["files_failed"] += 1

                    await (
                        firestore_repository
                        .persist_file_failure(
                            user_id=canvas_user_id,
                            course_id=course_id,
                            source_key=(
                                item.source_key
                            ),
                            canvas_file_id=file_id,
                            metadata_url=metadata_url,
                            error_type=error_type,
                        )
                    )

                    print(
                        "Canvas file processing "
                        "failed:",
                        file_id,
                        error_type,
                    )

    return stats