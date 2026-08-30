import asyncio
import json
import sys

import httpx


async def main() -> None:
    if len(sys.argv) < 4:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_rag_endpoint "
            "<user_id> <course_id> "
            "<question>"
        )

    user_id = sys.argv[1]
    course_id = sys.argv[2]
    question = " ".join(sys.argv[3:])

    payload = {
        "user_id": user_id,
        "course_id": course_id,
        "question": question,
        "source_limit": 8,
    }

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000",
        timeout=120.0,
    ) as client:
        response = await client.post(
            "/api/v1/rag/answer",
            json=payload,
        )

    print("HTTP status:", response.status_code)

    try:
        response_body = response.json()
    except ValueError:
        print(response.text)
        response.raise_for_status()
        return

    print(
        json.dumps(
            response_body,
            indent=2,
            ensure_ascii=False,
        )
    )

    response.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())