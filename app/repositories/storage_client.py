import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import storage


PROJECT_ROOT = (
    Path(__file__).resolve().parents[2]
)

load_dotenv(
    dotenv_path=PROJECT_ROOT / ".env"
)


_storage_client = None


def get_storage_client():
    global _storage_client

    if _storage_client is None:
        project_id = os.getenv(
            "GOOGLE_CLOUD_PROJECT"
        )

        if not project_id:
            raise RuntimeError(
                "GOOGLE_CLOUD_PROJECT is missing"
            )

        _storage_client = storage.Client(
            project=project_id.strip()
        )

    return _storage_client


def get_storage_bucket():
    bucket_name = os.getenv(
        "GCS_BUCKET_NAME"
    )

    if not bucket_name:
        raise RuntimeError(
            "GCS_BUCKET_NAME is missing"
        )

    return get_storage_client().bucket(
        bucket_name.strip()
    )