import asyncio
import uuid
from datetime import UTC, datetime

from app.connectors.gmail.parser import (
    ParsedEmail,
)
from app.repositories.firestore_client import (
    get_firestore_client,
)
from app.repositories.gmail_notification_repository import (
    GmailNotificationRepository,
)


async def cleanup(
    db,
    *,
    user_id: str,
) -> None:
    notifications_ref = (
        db.collection("users")
        .document(user_id)
        .collection("gmail_notifications")
    )

    async for snapshot in (
        notifications_ref.stream()
    ):
        await snapshot.reference.delete()

    await (
        db.collection("users")
        .document(user_id)
        .collection("integration_state")
        .document("gmail")
        .delete()
    )


async def main() -> None:
    db = get_firestore_client()
    repository = (
        GmailNotificationRepository(db)
    )
    user_id = (
        "gmail-notification-test-"
        f"{uuid.uuid4().hex}"
    )
    now = datetime.now(UTC)

    canvas_email = ParsedEmail(
        message_id="gmail-message-1",
        thread_id="gmail-thread-1",
        history_id="1001",
        internal_date=now,
        sent_at=now,
        subject=(
            "Canvas announcement: "
            "Lab 2 updated"
        ),
        from_address=(
            "notifications@instructure.com"
        ),
        to_addresses=(
            "student@example.com",
        ),
        cc_addresses=(),
        snippet=(
            "The lecturer uploaded revised "
            "instructions."
        ),
        text_body=(
            "Lab 2 instructions were updated. "
            "The deadline is unchanged."
        ),
        html_body=None,
        labels=("INBOX",),
        attachments=(),
    )

    unrelated_email = ParsedEmail(
        message_id="gmail-message-2",
        thread_id="gmail-thread-2",
        history_id="1002",
        internal_date=now,
        sent_at=now,
        subject="Your shopping receipt",
        from_address="store@example.com",
        to_addresses=(
            "student@example.com",
        ),
        cc_addresses=(),
        snippet="Thank you for your order.",
        text_body=(
            "Your order has been shipped."
        ),
        html_body=None,
        labels=("INBOX",),
        attachments=(),
    )

    try:
        first = await repository.persist_email(
            user_id=user_id,
            email=canvas_email,
        )

        assert first.relevance == "canvas"
        assert first.is_relevant is True
        assert first.published is False

        duplicate = (
            await repository.persist_email(
                user_id=user_id,
                email=canvas_email,
            )
        )

        assert duplicate.message_id == (
            first.message_id
        )
        assert duplicate.created_at == (
            first.created_at
        )

        unrelated = (
            await repository.persist_email(
                user_id=user_id,
                email=unrelated_email,
            )
        )

        assert (
            unrelated.relevance
            == "unrelated"
        )
        assert unrelated.is_relevant is False

        unpublished = await (
            repository
            .list_unpublished_relevant(
                user_id=user_id
            )
        )

        assert len(unpublished) == 1
        assert unpublished[0].message_id == (
            canvas_email.message_id
        )

        assert (
            await repository.load_history_id(
                user_id=user_id
            )
            is None
        )

        await repository.save_history_id(
            user_id=user_id,
            history_id="2001",
            account_email=(
                "student@example.com"
            ),
        )

        assert (
            await repository.load_history_id(
                user_id=user_id
            )
            == "2001"
        )

        await repository.mark_published(
            user_id=user_id,
            message_ids=[
                canvas_email.message_id
            ],
            notion_page_id=(
                "notion-page-test"
            ),
            notion_page_url=(
                "https://www.notion.so/"
                "notion-page-test"
            ),
        )

        remaining = await (
            repository
            .list_unpublished_relevant(
                user_id=user_id
            )
        )

        assert remaining == ()

        snapshots = [
            snapshot
            async for snapshot in (
                db.collection("users")
                .document(user_id)
                .collection(
                    "gmail_notifications"
                )
                .stream()
            )
        ]

        assert len(snapshots) == 2

        try:
            await repository.persist_email(
                user_id="invalid/user",
                email=canvas_email,
            )
        except ValueError:
            invalid_user_blocked = True
        else:
            invalid_user_blocked = False

        assert invalid_user_blocked

        print(
            {
                "status": "PASS",
                "stored_count": len(
                    snapshots
                ),
                "duplicate_blocked": True,
                "unrelated_filtered": True,
                "history_id": "2001",
                "publication_recorded": True,
                "invalid_user_blocked": (
                    invalid_user_blocked
                ),
            }
        )
    finally:
        await cleanup(
            db,
            user_id=user_id,
        )
        db.close()
        print("Test records cleaned up.")


if __name__ == "__main__":
    asyncio.run(main())