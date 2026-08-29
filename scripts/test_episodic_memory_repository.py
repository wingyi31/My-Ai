import asyncio
import uuid

from app.repositories.episodic_memory_repository import (
    EpisodicMemoryRepository,
)
from app.repositories.firestore_client import (
    get_firestore_client,
)


TEST_COURSE_ID = "course-123"


async def cleanup(
    db,
    *,
    user_id: str,
) -> None:
    events_ref = (
        db.collection("users")
        .document(user_id)
        .collection("episodes")
    )

    async for snapshot in events_ref.stream():
        await snapshot.reference.delete()


async def main() -> None:
    db = get_firestore_client()
    repository = EpisodicMemoryRepository(
        db
    )
    user_id = (
        "episodic-memory-test-"
        f"{uuid.uuid4().hex}"
    )

    try:
        generated = await (
            repository.record_event(
                user_id=user_id,
                course_id=TEST_COURSE_ID,
                session_id="session-123",
                event_type="summary.generated",
                entity_type="topic",
                entity_id="virtual-memory",
                payload={
                    "title": "Virtual Memory",
                },
            )
        )

        prepared = await (
            repository.record_event(
                user_id=user_id,
                course_id=TEST_COURSE_ID,
                session_id="session-123",
                event_type=(
                    "notion.publish_prepared"
                ),
                entity_type="topic",
                entity_id="virtual-memory",
                payload={
                    "summary_event_id": (
                        generated.event_id
                    ),
                },
            )
        )

        events = await (
            repository.list_recent_events(
                user_id=user_id,
                course_id=TEST_COURSE_ID,
            )
        )

        assert len(events) == 2
        assert events[0].event_id == (
            prepared.event_id
        )
        assert events[1].event_id == (
            generated.event_id
        )
        assert events[1].payload["title"] == (
            "Virtual Memory"
        )

        try:
            await repository.record_event(
                user_id=user_id,
                course_id=TEST_COURSE_ID,
                event_type="InvalidEvent",
            )
        except ValueError:
            invalid_type_blocked = True
        else:
            invalid_type_blocked = False

        assert invalid_type_blocked

        print(
            {
                "status": "PASS",
                "event_count": len(events),
                "event_types": [
                    event.event_type
                    for event in events
                ],
                "invalid_type_blocked": (
                    invalid_type_blocked
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