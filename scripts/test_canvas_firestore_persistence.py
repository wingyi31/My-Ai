import asyncio
import sys

from app.services.canvas_ingestion_service import (
    run_canvas_ingestion,
)


async def main() -> None:
    if len(sys.argv) != 3:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_canvas_firestore_persistence "
            "<user_id> <course_id>"
        )

    user_id = sys.argv[1]
    course_id = sys.argv[2]

    if not user_id.isdecimal():
        raise RuntimeError(
            "user_id must contain digits only"
        )

    if not course_id.isdecimal():
        raise RuntimeError(
            "course_id must contain digits only"
        )

    stats = await run_canvas_ingestion(
        canvas_user_id=user_id,
        course_id=course_id,
    )

    print()
    print("Firestore persistence completed")
    print(stats)


if __name__ == "__main__":
    asyncio.run(main())