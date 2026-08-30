from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass

from google.cloud.storage import Bucket

from app.connectors.canvas.client import (
    CanvasDownloadedFile,
)


@dataclass(frozen=True, slots=True)
class StoredObject:
    bucket_name: str
    object_name: str
    sha256: str
    size_bytes: int
    uploaded: bool


def safe_filename(filename: str) -> str:
    cleaned = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        filename.strip(),
    )

    return cleaned or "file.bin"


class CloudStorageRepository:
    def __init__(self, bucket: Bucket):
        self.bucket = bucket

    async def upload_canvas_file(
        self,
        *,
        user_id: str,
        course_id: str,
        downloaded_file: CanvasDownloadedFile,
    ) -> StoredObject:
        return await asyncio.to_thread(
            self._upload_canvas_file_sync,
            user_id,
            course_id,
            downloaded_file,
        )

    def _upload_canvas_file_sync(
        self,
        user_id: str,
        course_id: str,
        downloaded_file: CanvasDownloadedFile,
    ) -> StoredObject:
        file_hash = hashlib.sha256(
            downloaded_file.content
        ).hexdigest()

        filename = safe_filename(
            downloaded_file.filename
        )

        object_name = (
            f"users/{user_id}/"
            f"courses/{course_id}/"
            f"files/{downloaded_file.canvas_file_id}/"
            f"{filename}"
        )

        blob = self.bucket.blob(object_name)

        # Avoid uploading identical content again.
        if blob.exists():
            blob.reload()

            existing_hash = (
                blob.metadata or {}
            ).get("sha256")

            if existing_hash == file_hash:
                return StoredObject(
                    bucket_name=self.bucket.name,
                    object_name=object_name,
                    sha256=file_hash,
                    size_bytes=downloaded_file.size,
                    uploaded=False,
                )

        blob.metadata = {
            "sha256": file_hash,
            "canvas_file_id": (
                downloaded_file.canvas_file_id
            ),
            "canvas_course_id": str(course_id),
            "canvas_user_id": str(user_id),
        }

        blob.upload_from_string(
            downloaded_file.content,
            content_type=(
                downloaded_file.content_type
            ),
        )

        return StoredObject(
            bucket_name=self.bucket.name,
            object_name=object_name,
            sha256=file_hash,
            size_bytes=downloaded_file.size,
            uploaded=True,
        )

    async def download_object(
        self,
        object_name: str,
    ) -> bytes:
        return await asyncio.to_thread(
            self._download_object_sync,
            object_name,
        )

    def _download_object_sync(
        self,
        object_name: str,
    ) -> bytes:
        blob = self.bucket.blob(object_name)

        if not blob.exists():
            raise FileNotFoundError(
                f"Cloud Storage object not found: "
                f"gs://{self.bucket.name}/"
                f"{object_name}"
            )

        return blob.download_as_bytes()