import asyncio
import uuid

from app.repositories.firestore_client import (
    get_firestore_client,
)
from app.repositories.pending_notion_action_repository import (
    COMPLETED_STATUS,
    PendingNotionActionRepository,
    PendingNotionActionStateError,
)


async def cleanup(
    db,
    *,
    user_id: str,
) -> None:
    actions_ref = (
        db.collection("users")
        .document(user_id)
        .collection(
            "pending_notion_actions"
        )
    )

    async for snapshot in actions_ref.stream():
        await snapshot.reference.delete()


async def main() -> None:
    db = get_firestore_client()
    repository = (
        PendingNotionActionRepository(db)
    )
    user_id = (
        "pending-notion-test-"
        f"{uuid.uuid4().hex}"
    )

    try:
        action = await (
            repository.create_publish_action(
                user_id=user_id,
                course_id="course-123",
                session_id="session-123",
                summary_id="summary-123",
                title="Virtual Memory",
            )
        )

        assert action.status == "pending"
        assert action.summary_id == (
            "summary-123"
        )

        stored = await repository.get_action(
            user_id=user_id,
            action_id=action.action_id,
        )

        assert stored.title == "Virtual Memory"

        snapshot = await (
            db.collection("users")
            .document(user_id)
            .collection(
                "pending_notion_actions"
            )
            .document(action.action_id)
            .get()
        )
        stored_data = snapshot.to_dict() or {}

        assert "summary" not in stored_data
        assert "markdown" not in stored_data

        confirmable = await (
            repository
            .get_confirmable_action(
                user_id=user_id,
                action_id=action.action_id,
            )
        )

        assert confirmable.action_id == (
            action.action_id
        )

        await repository.mark_completed(
            user_id=user_id,
            action_id=action.action_id,
            notion_page_id="page-123",
            notion_page_url=(
                "https://www.notion.so/page-123"
            ),
        )

        completed = await repository.get_action(
            user_id=user_id,
            action_id=action.action_id,
        )

        assert (
            completed.status
            == COMPLETED_STATUS
        )
        assert completed.notion_page_id == (
            "page-123"
        )

        try:
            await (
                repository
                .get_confirmable_action(
                    user_id=user_id,
                    action_id=action.action_id,
                )
            )
        except PendingNotionActionStateError:
            repeated_confirmation_blocked = (
                True
            )
        else:
            repeated_confirmation_blocked = (
                False
            )

        assert repeated_confirmation_blocked

        print(
            {
                "status": "PASS",
                "action_status": (
                    completed.status
                ),
                "summary_content_stored": (
                    "summary" in stored_data
                    or "markdown" in stored_data
                ),
                "repeated_confirmation_blocked": (
                    repeated_confirmation_blocked
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