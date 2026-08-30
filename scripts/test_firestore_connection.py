import asyncio

from google.cloud import firestore

from app.core.gcp_settings import GcpSettings


async def main() -> None:
    settings = GcpSettings()

    print(
        "Firestore project being used:",
        repr(settings.project_id),
    )

    database = firestore.AsyncClient(
        project=settings.project_id,
    )

    document = (
        database
        .collection("system_checks")
        .document("local_connection")
    )

    await document.set(
        {
            "status": "ok",
            "source": "local-development",
            "checked_at": (
                firestore.SERVER_TIMESTAMP
            ),
        },
        merge=True,
    )

    snapshot = await document.get()

    if not snapshot.exists:
        raise RuntimeError(
            "Firestore document was not created"
        )

    data = snapshot.to_dict()

    print("Firestore connection successful")
    print("Document ID:", snapshot.id)
    print("Status:", data.get("status"))


if __name__ == "__main__":
    asyncio.run(main())