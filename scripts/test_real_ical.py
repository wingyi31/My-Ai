import asyncio
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


async def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"

    load_dotenv(env_path, override=True)

    url = (os.getenv("MYTIMES_ICAL_URL") or "").strip()

    print(f"Environment file: {env_path}")
    print(f"URL configured: {bool(url)}")
    print(
        "Valid protocol:",
        url.startswith(("http://", "https://")),
    )

    if not url:
        raise RuntimeError(
            f"MYTIMES_ICAL_URL is missing from {env_path}"
        )

    if url.startswith("webcal://"):
        url = "https://" + url.removeprefix("webcal://")

    if not url.startswith(("http://", "https://")):
        raise RuntimeError(
            "MYTIMES_ICAL_URL must start with https://"
        )

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        for attempt in range(1, 6):
            response = await client.get(
                url,
                headers={
                    "Accept": "text/calendar,*/*;q=0.8",
                    "User-Agent": "StudyOps-iCal-Connector/1.0",
                },
            )

            print(
                {
                    "attempt": attempt,
                    "status": response.status_code,
                    "bytes": len(response.content),
                    "content_type": response.headers.get("content-type"),
                    "retry_after": response.headers.get("retry-after"),
                }
            )

            if response.status_code == 202:
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            if response.status_code != 200:
                raise RuntimeError(
                    f"MyTIMeS returned HTTP {response.status_code}"
                )

            content = response.content.lstrip(
                b"\xef\xbb\xbf \t\r\n"
            )

            if not content.startswith(b"BEGIN:VCALENDAR"):
                raise RuntimeError(
                    "Response is not a valid iCalendar document"
                )

            if b"END:VCALENDAR" not in content:
                raise RuntimeError(
                    "Incomplete iCalendar document"
                )

            print("PASS: Real MyTIMeS calendar downloaded successfully")
            return

    raise RuntimeError(
        "MyTIMeS continued returning HTTP 202 without calendar content"
    )


if __name__ == "__main__":
    asyncio.run(main())