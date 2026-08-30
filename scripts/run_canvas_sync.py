import asyncio
import json
import sys

from dotenv import load_dotenv

from app.services.canvas_sync_orchestrator import (
    run_canvas_sync,
)


load_dotenv()


async def main() -> None:
    if len(sys.argv) != 3:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.run_canvas_sync "
            "<user_id> <course_id>"
        )

    user_id = sys.argv[1]
    course_id = sys.argv[2]

    result = await run_canvas_sync(
        canvas_user_id=user_id,
        course_id=course_id,
    )

    print()
    print("Canvas synchronization completed")
    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())