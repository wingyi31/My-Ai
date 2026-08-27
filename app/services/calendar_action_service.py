from __future__ import annotations

from dataclasses import dataclass
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from typing import Any

from app.connectors.calendar import (
    GoogleCalendarClient,
)
from app.repositories.pending_action_repository import (
    COMPLETED_STATUS,
    CREATE_CALENDAR_EVENT_ACTION,
    PENDING_STATUS,
    PendingActionRepository,
    PendingActionStateError,
    PendingCalendarAction,
)
from app.services.canvas_reader import (
    CanvasReadService,
)


ALLOWED_ASSIGNMENT_DATE_FIELDS = {
    "due_at",
    "lock_at",
    "unlock_at",
}


@dataclass(frozen=True)
class CalendarActionConfirmation:
    action: PendingCalendarAction
    already_completed: bool


class CalendarActionService:

    def __init__(
        self,
        *,
        canvas_read_service: CanvasReadService,
        calendar_client: GoogleCalendarClient,
        action_repository: (
            PendingActionRepository
        ),
    ) -> None:
        self._canvas_read_service = (
            canvas_read_service
        )
        self._calendar_client = (
            calendar_client
        )
        self._action_repository = (
            action_repository
        )

    async def prepare_assignment_event(
        self,
        *,
        user_id: str,
        course_id: str,
        assignment_query: str,
        date_field: str = "due_at",
    ) -> PendingCalendarAction:
        cleaned_user_id = str(
            user_id
        ).strip()
        cleaned_course_id = str(
            course_id
        ).strip()
        cleaned_query = (
            assignment_query.strip()
        )
        cleaned_date_field = (
            date_field.strip()
        )

        if not cleaned_user_id:
            raise ValueError(
                "User ID cannot be empty"
            )

        if not cleaned_course_id:
            raise ValueError(
                "Course ID cannot be empty"
            )

        if not cleaned_query:
            raise ValueError(
                "Assignment query cannot be empty"
            )

        if (
            cleaned_date_field
            not in ALLOWED_ASSIGNMENT_DATE_FIELDS
        ):
            raise ValueError(
                "Assignment date field must be "
                "due_at, lock_at, or unlock_at"
            )

        course_content = (
            await self
            ._canvas_read_service
            .course_content(
                cleaned_course_id
            )
        )

        item = self._find_assignment(
            course_content=course_content,
            query=cleaned_query,
        )

        date_value = item.get(
            cleaned_date_field
        )

        if (
            not isinstance(date_value, str)
            or not date_value
        ):
            title = item.get(
                "title",
                cleaned_query,
            )

            raise ValueError(
                f"{title} does not have a "
                f"{cleaned_date_field} value "
                "in Canvas"
            )

        target_time = self._parse_datetime(
            date_value
        )
        now = datetime.now(UTC)

        if target_time <= now:
            raise ValueError(
                "The selected assignment date has "
                "already passed"
            )

        if (
            target_time - now
            < timedelta(minutes=5)
        ):
            raise ValueError(
                "The selected assignment date is "
                "too close to create a useful "
                "Calendar reminder"
            )

        event_start = (
            target_time
            - timedelta(minutes=30)
        )

        if event_start <= now:
            event_start = (
                now + timedelta(minutes=1)
            )

        course = course_content.get(
            "course",
            {},
        )

        if not isinstance(course, dict):
            course = {}

        course_label = (
            course.get("course_code")
            or course.get("name")
            or cleaned_course_id
        )

        title = str(
            item.get("title")
            or cleaned_query
        ).strip()

        date_labels = {
            "due_at": "Deadline",
            "lock_at": "Canvas locks",
            "unlock_at": "Canvas unlocks",
        }

        date_label = date_labels[
            cleaned_date_field
        ]

        source_id = item.get("id")
        source_type = item.get(
            "item_type"
        )

        if source_id is None:
            raise ValueError(
                "Canvas item has no ID"
            )

        if (
            not isinstance(source_type, str)
            or not source_type
        ):
            source_type = "assignment"

        source_url = item.get("html_url")

        description_lines = [
            (
                "Created from a confirmed "
                "StudyOps action."
            ),
            f"Course: {course_label}",
            f"Item: {title}",
            (
                f"Canvas field: "
                f"{cleaned_date_field}"
            ),
            f"Canvas timestamp: {date_value}",
        ]

        if isinstance(source_url, str):
            description_lines.append(
                f"Canvas link: {source_url}"
            )

        event: dict[str, Any] = {
            "summary": (
                f"[{date_label}] "
                f"{course_label} - {title}"
            ),
            "description": "\n".join(
                description_lines
            ),
            "start": {
                "dateTime": (
                    event_start.isoformat()
                ),
            },
            "end": {
                "dateTime": (
                    target_time.isoformat()
                ),
            },
            "transparency": "transparent",
            "reminders": {
                "useDefault": True,
            },
        }

        if isinstance(source_url, str):
            event["source"] = {
                "title": (
                    "Canvas assignment"
                ),
                "url": source_url,
            }

        # Repeated proposals for the same Canvas
        # item, date field, and timestamp produce the
        # same Google Calendar event ID.
        idempotency_key = (
            f"canvas:{cleaned_course_id}:"
            f"{source_type}:"
            f"{source_id}:"
            f"{cleaned_date_field}:"
            f"{date_value}"
        )

        return await (
            self._action_repository
            .create_calendar_event_action(
                user_id=cleaned_user_id,
                course_id=(
                    cleaned_course_id
                ),
                event=event,
                source={
                    "source_type": source_type,
                    "source_id": source_id,
                    "source_title": title,
                    "date_field": (
                        cleaned_date_field
                    ),
                    "source_timestamp": (
                        date_value
                    ),
                    "source_url": source_url,
                },
                idempotency_key=(
                    idempotency_key
                ),
                expires_in_minutes=15,
            )
        )

    async def confirm_action(
        self,
        *,
        user_id: str,
        action_id: str,
    ) -> CalendarActionConfirmation:
        cleaned_user_id = str(
            user_id
        ).strip()
        cleaned_action_id = str(
            action_id
        ).strip()

        if not cleaned_user_id:
            raise ValueError(
                "User ID cannot be empty"
            )

        if not cleaned_action_id:
            raise ValueError(
                "Action ID cannot be empty"
            )

        existing = await (
            self._action_repository
            .get_action(
                user_id=cleaned_user_id,
                action_id=cleaned_action_id,
            )
        )

        if existing.status == COMPLETED_STATUS:
            return CalendarActionConfirmation(
                action=existing,
                already_completed=True,
            )

        if existing.status != PENDING_STATUS:
            raise PendingActionStateError(
                "Only a pending Calendar action "
                "can be confirmed"
            )

        action = await (
            self._action_repository
            .get_confirmable_action(
                user_id=cleaned_user_id,
                action_id=cleaned_action_id,
            )
        )

        if (
            action.action_type
            != CREATE_CALENDAR_EVENT_ACTION
        ):
            raise PendingActionStateError(
                "Unsupported pending action type"
            )

        calendar_event = await (
            self._calendar_client
            .create_event(
                event_id=action.event_id,
                event=action.event,
            )
        )

        calendar_event_id = (
            calendar_event.get("id")
        )

        if not isinstance(
            calendar_event_id,
            str,
        ):
            raise RuntimeError(
                "Google Calendar returned no "
                "event ID"
            )

        calendar_event_link = (
            calendar_event.get("htmlLink")
        )

        if not isinstance(
            calendar_event_link,
            str,
        ):
            calendar_event_link = None

        await (
            self._action_repository
            .mark_completed(
                user_id=cleaned_user_id,
                action_id=(
                    cleaned_action_id
                ),
                calendar_event_id=(
                    calendar_event_id
                ),
                calendar_event_link=(
                    calendar_event_link
                ),
            )
        )

        completed = await (
            self._action_repository
            .get_action(
                user_id=cleaned_user_id,
                action_id=(
                    cleaned_action_id
                ),
            )
        )

        return CalendarActionConfirmation(
            action=completed,
            already_completed=False,
        )

    async def cancel_action(
        self,
        *,
        user_id: str,
        action_id: str,
    ) -> None:
        cleaned_user_id = str(
            user_id
        ).strip()
        cleaned_action_id = str(
            action_id
        ).strip()

        if not cleaned_user_id:
            raise ValueError(
                "User ID cannot be empty"
            )

        if not cleaned_action_id:
            raise ValueError(
                "Action ID cannot be empty"
            )

        await (
            self._action_repository
            .cancel_action(
                user_id=cleaned_user_id,
                action_id=cleaned_action_id,
            )
        )

    @classmethod
    def _find_assignment(
        cls,
        *,
        course_content: dict[str, Any],
        query: str,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []

        assignments = course_content.get(
            "assignments",
            [],
        )

        if isinstance(assignments, list):
            for assignment in assignments:
                if not isinstance(
                    assignment,
                    dict,
                ):
                    continue

                items.append(
                    {
                        **assignment,
                        "title": (
                            assignment.get("name")
                        ),
                        "item_type": (
                            "assignment"
                        ),
                    }
                )

        quizzes = course_content.get(
            "quizzes",
            [],
        )

        if isinstance(quizzes, list):
            for quiz in quizzes:
                if not isinstance(quiz, dict):
                    continue

                items.append(
                    {
                        **quiz,
                        "item_type": "quiz",
                    }
                )

        normalized_query = (
            cls._normalize_text(query)
        )

        exact_matches = [
            item
            for item in items
            if cls._normalize_text(
                str(
                    item.get("title", "")
                )
            )
            == normalized_query
        ]

        if len(exact_matches) == 1:
            return exact_matches[0]

        direct_matches = [
            item
            for item in items
            if cls._direct_match(
                normalized_query,
                cls._normalize_text(
                    str(
                        item.get(
                            "title",
                            "",
                        )
                    )
                ),
            )
        ]

        if len(direct_matches) == 1:
            return direct_matches[0]

        query_tokens = set(
            normalized_query.split()
        )
        scored: list[
            tuple[float, dict[str, Any]]
        ] = []

        for item in items:
            title = cls._normalize_text(
                str(item.get("title", ""))
            )
            title_tokens = set(
                title.split()
            )

            if not title_tokens:
                continue

            overlap = len(
                query_tokens & title_tokens
            )
            score = (
                overlap / len(title_tokens)
            )

            if score >= 0.5:
                scored.append(
                    (score, item)
                )

        scored.sort(
            key=lambda match: match[0],
            reverse=True,
        )

        if scored:
            best_score = scored[0][0]
            best_matches = [
                item
                for score, item in scored
                if score == best_score
            ]

            if len(best_matches) == 1:
                return best_matches[0]

        available = [
            str(item.get("title"))
            for item in items
            if item.get("title")
        ]

        if not available:
            raise ValueError(
                "No assignments or quizzes were "
                "found for this course"
            )

        raise ValueError(
            "Could not uniquely identify the "
            "assignment. Available items: "
            + ", ".join(available)
        )

    @staticmethod
    def _direct_match(
        query: str,
        title: str,
    ) -> bool:
        if not query or not title:
            return False

        return (
            query in title
            or title in query
        )

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        normalized = "".join(
            character
            if character.isalnum()
            else " "
            for character in value.casefold()
        )

        return " ".join(
            normalized.split()
        )

    @staticmethod
    def _parse_datetime(
        value: str,
    ) -> datetime:
        try:
            parsed = datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )
        except ValueError as exc:
            raise ValueError(
                "Canvas returned an invalid "
                "assignment timestamp"
            ) from exc

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=UTC
            )

        return parsed.astimezone(UTC)