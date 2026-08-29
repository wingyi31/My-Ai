import asyncio
import uuid

from app.repositories.conversation_repository import (
    ConversationRepository,
    ConversationSessionMismatchError,
)
from app.repositories.firestore_client import (
    get_firestore_client,
)


TEST_USER_ID = "conversation-repository-test"
TEST_COURSE_ID = "course-123"


async def cleanup(
    db,
    *,
    session_id: str,
) -> None:
    conversation_ref = (
        db.collection("users")
        .document(TEST_USER_ID)
        .collection("conversations")
        .document(session_id)
    )

    async for snapshot in (
        conversation_ref
        .collection("messages")
        .stream()
    ):
        await snapshot.reference.delete()

    await conversation_ref.delete()


async def main() -> None:
    db = get_firestore_client()
    repository = ConversationRepository(db)
    session_id = (
        "repository-test-"
        f"{uuid.uuid4().hex}"
    )

    try:
        initial_messages = (
            await repository
            .load_recent_messages(
                user_id=TEST_USER_ID,
                course_id=TEST_COURSE_ID,
                session_id=session_id,
            )
        )

        assert initial_messages == ()

        await repository.append_turn(
            user_id=TEST_USER_ID,
            course_id=TEST_COURSE_ID,
            session_id=session_id,
            user_message="Explain RAID.",
            assistant_message=(
                "RAID combines multiple drives."
            ),
        )

        await repository.append_turn(
            user_id=TEST_USER_ID,
            course_id=TEST_COURSE_ID,
            session_id=session_id,
            user_message=(
                "Which type provides redundancy?"
            ),
            assistant_message=(
                "RAID 1 provides mirroring."
            ),
        )

        messages = (
            await repository
            .load_recent_messages(
                user_id=TEST_USER_ID,
                course_id=TEST_COURSE_ID,
                session_id=session_id,
                limit=10,
            )
        )

        conversations = (
            await repository.list_conversations(
                user_id=TEST_USER_ID,
                course_id=TEST_COURSE_ID,
            )
        )

        summary = next(
            conversation
            for conversation in conversations
            if conversation.session_id
            == session_id
        )

        assert summary.course_id == (
            TEST_COURSE_ID
        )
        assert summary.title == (
            "Explain RAID."
        )

        assert len(messages) == 4
        assert [
            message.role
            for message in messages
        ] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert messages[0].content == (
            "Explain RAID."
        )
        assert messages[-1].content == (
            "RAID 1 provides mirroring."
        )

        try:
            await repository.load_recent_messages(
                user_id=TEST_USER_ID,
                course_id="different-course",
                session_id=session_id,
            )
        except (
            ConversationSessionMismatchError
        ):
            mismatch_blocked = True
        else:
            mismatch_blocked = False

        assert mismatch_blocked

        print(
            {
                "status": "PASS",
                "message_count": len(messages),
                "roles": [
                    message.role
                    for message in messages
                ],
                "course_mismatch_blocked": (
                    mismatch_blocked
                ),
            }
        )
    finally:
        await cleanup(
            db,
            session_id=session_id,
        )
        db.close()
        print("Test records cleaned up.")


if __name__ == "__main__":
    asyncio.run(main())