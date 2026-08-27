from __future__ import annotations

import hashlib
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector

from datetime import (
    datetime,
    timedelta,
    timezone,
)


def stable_id(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


class CanvasFirestoreRepository:

    def __init__(self, db):
        self.db = db

    def _course_ref(
        self,
        *,
        user_id: str,
        course_id: str,
    ):
        return (
            self.db
            .collection("users")
            .document(str(user_id))
            .collection("canvas_courses")
            .document(str(course_id))
        )

    def _source_ref(
        self,
        *,
        user_id: str,
        course_id: str,
        source_key: str,
    ):
        return (
            self._course_ref(
                user_id=user_id,
                course_id=course_id,
            )
            .collection("sources")
            .document(stable_id(source_key))
        )

    def _file_ref(
        self,
        *,
        user_id: str,
        course_id: str,
        canvas_file_id: str,
    ):
        return (
            self._course_ref(
                user_id=user_id,
                course_id=course_id,
            )
            .collection("files")
            .document(str(canvas_file_id))
        )

    def _chunks_ref(
        self,
        *,
        user_id: str,
        course_id: str,
        canvas_file_id: str,
    ):
        return (
            self._file_ref(
                user_id=user_id,
                course_id=course_id,
                canvas_file_id=canvas_file_id,
            )
            .collection("chunks")
        )

    def _sync_lease_ref(
        self,
        *,
        user_id: str,
        course_id: str,
    ):
        return (
            self._course_ref(
                user_id=user_id,
                course_id=course_id,
            )
            .collection("locks")
            .document("canvas_sync")
        )

    async def mark_course_synced(
        self,
        *,
        user_id: str,
        course_id: str,
    ) -> None:
        course_ref = self._course_ref(
            user_id=user_id,
            course_id=course_id,
        )

        await course_ref.set(
            {
                "canvas_user_id": str(user_id),
                "canvas_course_id": str(course_id),
                "source": "canvas",
                "synced_at": (
                    firestore.SERVER_TIMESTAMP
                ),
            },
            merge=True,
        )

    async def get_revision_hash(
        self,
        *,
        user_id: str,
        course_id: str,
        source_key: str,
    ) -> str | None:
        source_ref = self._source_ref(
            user_id=user_id,
            course_id=course_id,
            source_key=source_key,
        )

        snapshot = await source_ref.get()

        if not snapshot.exists:
            return None

        stored_data = snapshot.to_dict() or {}

        return stored_data.get(
            "revision_hash"
        )

    async def persist_item(
        self,
        *,
        user_id: str,
        course_id: str,
        item: Any,
        revision_hash: str,
    ) -> None:
        source_ref = self._source_ref(
            user_id=user_id,
            course_id=course_id,
            source_key=item.source_key,
        )

        # Convert the Pydantic model into
        # Firestore-safe data.
        data = item.model_dump(
            mode="json"
        )

        # Preserve due_at as a native
        # Firestore timestamp.
        if item.due_at is not None:
            data["due_at"] = item.due_at

        data.update(
            {
                "canvas_user_id": str(
                    user_id
                ),
                "canvas_course_id": str(
                    course_id
                ),
                "revision_hash": (
                    revision_hash
                ),
                "synced_at": (
                    firestore.SERVER_TIMESTAMP
                ),
            }
        )

        await source_ref.set(
            data,
            merge=True,
        )

    async def persist_file_upload(
        self,
        *,
        user_id: str,
        course_id: str,
        source_key: str,
        canvas_file_id: str,
        metadata_url: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        storage_bucket: str,
        storage_object: str,
    ) -> None:
        file_ref = self._file_ref(
            user_id=user_id,
            course_id=course_id,
            canvas_file_id=canvas_file_id,
        )

        await file_ref.set(
            {
                "canvas_file_id": str(
                    canvas_file_id
                ),
                "canvas_course_id": str(
                    course_id
                ),
                "canvas_user_id": str(
                    user_id
                ),
                "filename": filename,
                "content_type": (
                    content_type
                ),
                "size_bytes": size_bytes,
                "sha256": sha256,
                "metadata_url": metadata_url,
                "linked_source_keys": (
                    firestore.ArrayUnion(
                        [source_key]
                    )
                ),
                "storage_bucket": (
                    storage_bucket
                ),
                "storage_object": (
                    storage_object
                ),
                "upload_status": "uploaded",
                "last_error_type": None,
                "storage_synced_at": (
                    firestore.SERVER_TIMESTAMP
                ),
            },
            merge=True,
        )

    async def persist_file_failure(
        self,
        *,
        user_id: str,
        course_id: str,
        source_key: str,
        canvas_file_id: str,
        metadata_url: str,
        error_type: str,
    ) -> None:
        file_ref = self._file_ref(
            user_id=user_id,
            course_id=course_id,
            canvas_file_id=canvas_file_id,
        )

        await file_ref.set(
            {
                "canvas_file_id": str(
                    canvas_file_id
                ),
                "canvas_course_id": str(
                    course_id
                ),
                "canvas_user_id": str(
                    user_id
                ),
                "metadata_url": metadata_url,
                "linked_source_keys": (
                    firestore.ArrayUnion(
                        [source_key]
                    )
                ),
                "upload_status": "failed",
                "last_error_type": error_type,
                "last_attempt_at": (
                    firestore.SERVER_TIMESTAMP
                ),
            },
            merge=True,
        )

    async def get_file_record(
        self,
        *,
        user_id: str,
        course_id: str,
        canvas_file_id: str,
    ) -> dict[str, Any] | None:
        file_ref = self._file_ref(
            user_id=user_id,
            course_id=course_id,
            canvas_file_id=canvas_file_id,
        )

        snapshot = await file_ref.get()

        if not snapshot.exists:
            return None

        return snapshot.to_dict()

    async def list_course_files(
        self,
        *,
        user_id: str,
        course_id: str,
        uploaded_only: bool = True,
    ) -> list[dict[str, Any]]:
        files_collection = (
            self._course_ref(
                user_id=user_id,
                course_id=course_id,
            )
            .collection("files")
        )

        records: list[
            dict[str, Any]
        ] = []

        async for snapshot in (
            files_collection.stream()
        ):
            data = snapshot.to_dict() or {}

            # Fall back to the Firestore document
            # ID if the field is missing.
            data["canvas_file_id"] = str(
                data.get("canvas_file_id")
                or snapshot.id
            )

            if (
                uploaded_only
                and data.get("upload_status")
                != "uploaded"
            ):
                continue

            records.append(data)

        # Ensure deterministic processing order.
        records.sort(
            key=lambda record: str(
                record.get(
                    "canvas_file_id",
                    "",
                )
            )
        )

        return records

    async def acquire_course_sync_lease(
        self,
        *,
        user_id: str,
        course_id: str,
        owner_id: str,
        lease_seconds: int,
    ) -> bool:
        owner_id = owner_id.strip()

        if not owner_id:
            raise ValueError(
                "Lease owner_id cannot be empty"
            )

        if lease_seconds < 60:
            raise ValueError(
                "Lease must last at least "
                "60 seconds"
            )

        lease_ref = self._sync_lease_ref(
            user_id=user_id,
            course_id=course_id,
        )

        now = datetime.now(
            timezone.utc
        )
        expires_at = now + timedelta(
            seconds=lease_seconds
        )

        transaction = self.db.transaction()

        @firestore.async_transactional
        async def acquire(
            transaction,
        ) -> bool:
            snapshot = await lease_ref.get(
                transaction=transaction
            )

            if snapshot.exists:
                data = (
                    snapshot.to_dict()
                    or {}
                )

                current_expiry = data.get(
                    "expires_at"
                )

                if isinstance(
                    current_expiry,
                    datetime,
                ):
                    if (
                        current_expiry.tzinfo
                        is None
                    ):
                        current_expiry = (
                            current_expiry
                            .replace(
                                tzinfo=timezone.utc
                            )
                        )

                    if current_expiry > now:
                        return False

            transaction.set(
                lease_ref,
                {
                    "canvas_user_id": str(
                        user_id
                    ),
                    "canvas_course_id": str(
                        course_id
                    ),
                    "owner_id": owner_id,
                    "acquired_at": now,
                    "expires_at": expires_at,
                },
            )

            return True

        return await acquire(transaction)

    async def release_course_sync_lease(
        self,
        *,
        user_id: str,
        course_id: str,
        owner_id: str,
    ) -> bool:
        lease_ref = self._sync_lease_ref(
            user_id=user_id,
            course_id=course_id,
        )

        transaction = self.db.transaction()

        @firestore.async_transactional
        async def release(
            transaction,
        ) -> bool:
            snapshot = await lease_ref.get(
                transaction=transaction
            )

            if not snapshot.exists:
                return False

            data = snapshot.to_dict() or {}

            if (
                data.get("owner_id")
                != owner_id
            ):
                return False

            transaction.delete(
                lease_ref
            )

            return True

        return await release(transaction)

    async def replace_file_chunks(
        self,
        *,
        user_id: str,
        course_id: str,
        canvas_file_id: str,
        filename: str,
        file_sha256: str,
        page_count: int,
        total_characters: int,
        chunks: list[Any],
    ) -> None:
        file_ref = self._file_ref(
            user_id=user_id,
            course_id=course_id,
            canvas_file_id=canvas_file_id,
        )

        chunks_collection = (
            self._chunks_ref(
                user_id=user_id,
                course_id=course_id,
                canvas_file_id=(
                    canvas_file_id
                ),
            )
        )

        # Remove chunks belonging to an
        # older PDF revision.
        existing_chunks = [
            snapshot
            async for snapshot
            in chunks_collection.stream()
        ]

        for start in range(
            0,
            len(existing_chunks),
            400,
        ):
            batch = self.db.batch()

            for snapshot in existing_chunks[
                start:start + 400
            ]:
                batch.delete(
                    snapshot.reference
                )

            await batch.commit()

        # Write the newly extracted chunks.
        for start in range(
            0,
            len(chunks),
            400,
        ):
            batch = self.db.batch()

            for chunk in chunks[
                start:start + 400
            ]:
                chunk_ref = (
                    chunks_collection.document(
                        chunk.chunk_id
                    )
                )

                batch.set(
                    chunk_ref,
                    {
                        "canvas_user_id": str(
                            user_id
                        ),
                        "canvas_course_id": str(
                            course_id
                        ),
                        "canvas_file_id": str(
                            canvas_file_id
                        ),
                        "filename": filename,
                        "page_number": (
                            chunk.page_number
                        ),
                        "chunk_index": (
                            chunk.chunk_index
                        ),
                        "text": chunk.text,
                        "text_hash": (
                            chunk.text_hash
                        ),
                        "start_character": (
                            chunk.start_character
                        ),
                        "end_character": (
                            chunk.end_character
                        ),
                        "file_sha256": (
                            file_sha256
                        ),
                        "created_at": (
                            firestore
                            .SERVER_TIMESTAMP
                        ),
                    },
                )

            await batch.commit()

        await file_ref.set(
            {
                "extraction_status": (
                    "complete"
                ),
                "extraction_method": (
                    "pypdf"
                ),
                "extraction_sha256": (
                    file_sha256
                ),
                "extracted_page_count": (
                    page_count
                ),
                "extracted_character_count": (
                    total_characters
                ),
                "chunk_count": len(chunks),
                "needs_ocr": False,
                "extracted_at": (
                    firestore.SERVER_TIMESTAMP
                ),
            },
            merge=True,
        )

    async def list_file_chunks(
        self,
        *,
        user_id: str,
        course_id: str,
        canvas_file_id: str,
    ) -> list[dict[str, Any]]:
        chunks_collection = (
            self._chunks_ref(
                user_id=user_id,
                course_id=course_id,
                canvas_file_id=(
                    canvas_file_id
                ),
            )
        )

        chunks: list[
            dict[str, Any]
        ] = []

        query = chunks_collection.order_by(
            "chunk_index"
        )

        async for snapshot in query.stream():
            data = snapshot.to_dict() or {}

            data["chunk_id"] = (
                snapshot.id
            )

            chunks.append(data)

        return chunks

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
        if not embedding:
            raise ValueError(
                "Embedding cannot be empty"
            )

        if len(embedding) > 2048:
            raise ValueError(
                "Firestore supports embedding "
                "dimensions up to 2048"
            )

        chunk_ref = (
            self._chunks_ref(
                user_id=user_id,
                course_id=course_id,
                canvas_file_id=(
                    canvas_file_id
                ),
            )
            .document(str(chunk_id))
        )

        await chunk_ref.set(
            {
                "embedding": Vector(
                    embedding
                ),
                "embedding_model": (
                    embedding_model
                ),
                "embedding_dimensions": (
                    len(embedding)
                ),
                "embedding_text_hash": (
                    text_hash
                ),
                "embedded_at": (
                    firestore.SERVER_TIMESTAMP
                ),
            },
            merge=True,
        )