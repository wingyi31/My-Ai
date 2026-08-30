from __future__ import annotations

import asyncio
from datetime import (
    UTC,
    datetime,
    timedelta,
)

from app.repositories.firestore_client import (
    get_firestore_client,
)
from app.repositories.pending_action_repository import (
    PendingActionRepository,
)


async def main() -> None:
    repository = PendingActionRepository(
        get_firestore_client()
    )

    due_at = (
        datetime.now(UTC)
        + timedelta(days=1)
    )
    start_at = (
        due_at
        - timedelta(minutes=30)
    )

    action = await (
        repository
        .create_calendar_event_action(
            user_id="126345",
            course_id="96996",
            event={
                "summary": (
                    "[Test] StudyOps pending action"
                ),
                "description": (
                    "This is only a pending-action "
                    "repository test."
                ),
                "start": {
                    "dateTime": (
                        start_at.isoformat()
                    ),
                },
                "end": {
                    "dateTime": (
                        due_at.isoformat()
                    ),
                },
                "transparency": "transparent",
            },
            source={
                "source_type": "test",
                "assignment_id": "test",
            },
            expires_in_minutes=5,
        )
    )

    loaded = await repository.get_action(
        user_id=action.user_id,
        action_id=action.action_id,
    )

    print(
        "Action ID created:",
        bool(loaded.action_id),
    )
    print(
        "Status:",
        loaded.status,
    )
    print(
        "Action type:",
        loaded.action_type,
    )
    print(
        "Event summary:",
        loaded.event.get("summary"),
    )
    print(
        "Pending-action repository: OK"
    )


if __name__ == "__main__":
    asyncio.run(main())