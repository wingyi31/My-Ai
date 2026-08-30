from google.cloud import firestore

from app.core.config import get_settings


_firestore_client: (
    firestore.AsyncClient | None
) = None


def get_firestore_client() -> (
    firestore.AsyncClient
):
    global _firestore_client

    if _firestore_client is None:
        settings = get_settings()

        _firestore_client = (
            firestore.AsyncClient(
                project=(
                    settings.google_cloud_project
                ),
                database=(
                    settings.firestore_database
                ),
            )
        )

    return _firestore_client