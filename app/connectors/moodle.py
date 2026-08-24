from typing import Any

import httpx


class MoodleNotConfiguredError(RuntimeError):
    pass


class MoodleApiError(RuntimeError):
    pass


class MoodleClient:
    """Small asynchronous client for Moodle's REST External Services API."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        base_url: str,
        token: str | None,
    ) -> None:
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")
        self._token = token

    async def call(self, function: str, **parameters: Any) -> Any:
        if not self._token:
            raise MoodleNotConfiguredError(
                "MYTIMES_TOKEN is missing. Obtain a Taylor's-approved read-only "
                "Moodle web-service token or use the iCal fallback."
            )

        form = {
            "wstoken": self._token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
            **parameters,
        }

        try:
            response = await self._http_client.post(
                f"{self._base_url}/webservice/rest/server.php",
                data=form,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MoodleApiError(
                f"MyTIMeS HTTP request failed for {function}: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise MoodleApiError(
                "MyTIMeS returned a non-JSON response. The site may have redirected "
                "to SSO or disabled REST web services."
            ) from exc

        if isinstance(payload, dict) and payload.get("exception"):
            error_code = payload.get("errorcode", "unknown")
            message = payload.get("message", "Unknown Moodle API error")
            raise MoodleApiError(
                f"MyTIMeS rejected {function} [{error_code}]: {message}"
            )

        return payload

    async def get_site_info(self) -> dict[str, Any]:
        payload = await self.call("core_webservice_get_site_info")
        if not isinstance(payload, dict):
            raise MoodleApiError("Unexpected site-info response type")
        return payload

    async def list_user_courses(self, user_id: int) -> list[dict[str, Any]]:
        payload = await self.call(
            "core_enrol_get_users_courses",
            userid=user_id,
        )
        if not isinstance(payload, list):
            raise MoodleApiError("Unexpected course-list response type")
        return payload

    async def get_course_contents(self, course_id: int) -> list[dict[str, Any]]:
        payload = await self.call(
            "core_course_get_contents",
            courseid=course_id,
        )
        if not isinstance(payload, list):
            raise MoodleApiError("Unexpected course-content response type")
        return payload
