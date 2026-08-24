from datetime import UTC, datetime

from app.connectors.moodle import MoodleApiError, MoodleClient


class MyTimesSyncService:
    """First vertical slice: authenticate and list accessible course metadata."""

    def __init__(self, client: MoodleClient) -> None:
        self._client = client

    async def preview_metadata_sync(self) -> dict:
        site_info = await self._client.get_site_info()
        user_id = site_info.get("userid")
        if not isinstance(user_id, int):
            raise MoodleApiError("Site info did not contain a valid Moodle user ID")

        courses = await self._client.list_user_courses(user_id)
        course_preview = [
            {
                "id": course.get("id"),
                "shortname": course.get("shortname"),
                "fullname": course.get("fullname"),
            }
            for course in courses[:20]
        ]

        return {
            "status": "success",
            "source": "mytimes",
            "synced_at": datetime.now(UTC).isoformat(),
            "site_name": site_info.get("sitename"),
            "user_id": user_id,
            "course_count": len(courses),
            "courses": course_preview,
            "note": (
                "This first slice lists metadata only. The next slice will compare "
                "course contents, download new files, and persist sync state."
            ),
        }
