from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Iterable
from datetime import UTC, datetime
from typing import Any

from app.connectors.canvas import CanvasApiError, CanvasClient


class CanvasReadService:
    """Shape Canvas course data into a small, read-oriented response."""

    CATEGORY_KEYS = (
        "lectures",
        "tutorials",
        "assignments",
        "quizzes",
        "discussions",
        "readings",
        "announcements",
        "other",
    )

    def __init__(
        self,
        client: CanvasClient,
        *,
        max_concurrent_courses: int = 3,
    ) -> None:
        self._client = client
        self._max_concurrent_courses = max(1, max_concurrent_courses)

    async def profile(self) -> dict[str, Any]:
        profile = await self._client.get_current_user()
        return self._pick(profile, "id", "name", "short_name", "login_id")

    async def courses(self, *, include_completed: bool = False) -> dict[str, Any]:
        courses = await self._client.list_courses(include_completed=include_completed)
        shaped = [self._course(course) for course in courses]
        return {
            "access_mode": "read-only",
            "course_count": len(shaped),
            "courses": shaped,
        }

    async def course_content(self, course_id: str | int) -> dict[str, Any]:
        course = await self._client.get_course(course_id)
        return await self._course_content(course)

    async def active_course_details(self) -> dict[str, Any]:
        """Discover active courses, then dynamically load each course's details."""
        courses = await self._client.list_courses(include_completed=False)
        semaphore = asyncio.Semaphore(self._max_concurrent_courses)

        async def load(course: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await self._course_content(course)

        details = await asyncio.gather(*(load(course) for course in courses))
        deadlines = [
            {
                "course_id": detail["course"].get("id"),
                "course_name": detail["course"].get("name"),
                **deadline,
            }
            for detail in details
            for deadline in detail["deadlines"]
        ]
        deadlines.sort(key=self._deadline_sort_key)
        upcoming_deadlines = [
            deadline for deadline in deadlines if self._is_upcoming(deadline)
        ]

        return {
            "access_mode": "read-only",
            "generated_at": datetime.now(UTC).isoformat(),
            "course_count": len(details),
            "courses": details,
            "deadlines": deadlines,
            "upcoming_deadlines": upcoming_deadlines,
        }

    async def _course_content(self, course: dict[str, Any]) -> dict[str, Any]:
        course_id = course.get("id")
        if course_id is None:
            raise CanvasApiError("Canvas course response did not contain an ID")

        warnings: list[str] = []
        term = course.get("term")
        term_start = term.get("start_at") if isinstance(term, dict) else None
        announcement_start = self._announcement_start(
            course.get("start_at") or term_start
        )
        announcement_end = datetime.now(UTC).isoformat()

        modules, assignments, quizzes, files, announcements = await asyncio.gather(
            self._read_optional(
                self._client.list_modules(course_id),
                "modules",
                warnings,
            ),
            self._read_optional(
                self._client.list_assignments(course_id),
                "assignments",
                warnings,
            ),
            self._read_optional(
                self._client.list_quizzes(course_id),
                "quizzes",
                warnings,
                ignore_statuses={404},
            ),
            self._read_optional(
                self._client.list_files(course_id),
                "files",
                warnings,
            ),
            self._read_optional(
                self._client.list_announcements(
                    course_id,
                    start_date=announcement_start,
                    end_date=announcement_end,
                ),
                "announcements",
                warnings,
            ),
        )

        shaped_modules = [self._module(module) for module in modules]
        shaped_assignment_records = [
            self._assignment(assignment) for assignment in assignments
        ]
        shaped_assignments = [
            item
            for item in shaped_assignment_records
            if item["category"] == "assignment"
        ]
        shaped_quizzes = [self._quiz(quiz) for quiz in quizzes]
        quiz_assignments = {
            str(item["id"]): item
            for item in shaped_assignment_records
            if item["category"] == "quiz" and item.get("id") is not None
        }
        for quiz in shaped_quizzes:
            assignment = quiz_assignments.get(str(quiz.get("assignment_id")))
            if assignment is not None:
                # The assignment endpoint reflects due-date overrides for this user.
                for date_key in ("due_at", "unlock_at", "lock_at", "deadline"):
                    quiz[date_key] = assignment.get(date_key)
        classic_quiz_assignment_ids = {
            str(quiz["assignment_id"])
            for quiz in shaped_quizzes
            if quiz.get("assignment_id") is not None
        }
        shaped_quizzes.extend(
            self._assignment_as_quiz(item)
            for item in shaped_assignment_records
            if item["category"] == "quiz"
            and str(item.get("id")) not in classic_quiz_assignment_ids
        )
        shaped_files = [self._file(file) for file in files]
        shaped_announcements = [
            self._announcement(announcement) for announcement in announcements
        ]
        categories = self._categories(
            shaped_modules,
            shaped_assignments,
            shaped_quizzes,
            shaped_files,
            shaped_announcements,
        )
        deadlines = self._deadlines(
            shaped_modules,
            shaped_assignments,
            shaped_quizzes,
        )
        upcoming_deadlines = [
            deadline for deadline in deadlines if self._is_upcoming(deadline)
        ]

        return {
            "access_mode": "read-only",
            "course": self._course(course),
            "modules": shaped_modules,
            "lectures": categories["lectures"],
            "tutorials": categories["tutorials"],
            "assignments": shaped_assignments,
            "quizzes": shaped_quizzes,
            "announcements": shaped_announcements,
            "files": shaped_files,
            "categories": categories,
            "deadlines": deadlines,
            "upcoming_deadlines": upcoming_deadlines,
            "warnings": warnings,
        }

    @staticmethod
    async def _read_optional(
        operation: Awaitable[list[dict[str, Any]]],
        label: str,
        warnings: list[str],
        ignore_statuses: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return await operation
        except CanvasApiError as exc:
            if ignore_statuses and exc.status_code in ignore_statuses:
                return []
            warnings.append(f"Could not read {label}: {exc}")
            return []

    @classmethod
    def _course(cls, course: dict[str, Any]) -> dict[str, Any]:
        shaped = cls._pick(
            course,
            "id",
            "name",
            "course_code",
            "workflow_state",
            "start_at",
            "end_at",
            "html_url",
            "is_favorite",
        )
        term = course.get("term")
        if isinstance(term, dict):
            shaped["term"] = cls._pick(term, "id", "name", "start_at", "end_at")
        return shaped

    @classmethod
    def _module(cls, module: dict[str, Any]) -> dict[str, Any]:
        shaped = cls._pick(
            module,
            "id",
            "name",
            "position",
            "unlock_at",
            "state",
            "published",
        )
        items = module.get("items")
        shaped["items"] = (
            [
                cls._module_item(item, str(module.get("name", "")))
                for item in items
                if isinstance(item, dict)
            ]
            if isinstance(items, list)
            else []
        )
        return shaped

    @classmethod
    def _module_item(
        cls,
        item: dict[str, Any],
        module_name: str,
    ) -> dict[str, Any]:
        shaped = cls._pick(
            item,
            "id",
            "title",
            "type",
            "position",
            "content_id",
            "html_url",
            "url",
            "published",
        )
        shaped["category"] = cls._category(
            str(item.get("type", "")),
            str(item.get("title", "")),
            module_name,
        )
        details = item.get("content_details")
        if isinstance(details, dict):
            shaped["content_details"] = cls._pick(
                details,
                "points_possible",
                "due_at",
                "unlock_at",
                "lock_at",
                "locked_for_user",
                "lock_explanation",
            )
        shaped["deadline"] = (
            details.get("due_at") if isinstance(details, dict) else None
        )
        return shaped

    @classmethod
    def _assignment(cls, assignment: dict[str, Any]) -> dict[str, Any]:
        shaped = cls._pick(
            assignment,
            "id",
            "name",
            "description",
            "due_at",
            "unlock_at",
            "lock_at",
            "points_possible",
            "submission_types",
            "allowed_extensions",
            "html_url",
            "is_quiz_assignment",
            "published",
            "locked_for_user",
            "lock_explanation",
        )
        submission_types = assignment.get("submission_types")
        is_quiz = bool(assignment.get("is_quiz_assignment")) or (
            isinstance(submission_types, list) and "online_quiz" in submission_types
        )
        shaped["category"] = "quiz" if is_quiz else "assignment"
        shaped["deadline"] = assignment.get("due_at")
        return shaped

    @classmethod
    def _assignment_as_quiz(cls, assignment: dict[str, Any]) -> dict[str, Any]:
        quiz = dict(assignment)
        quiz["title"] = quiz.pop("name", None)
        quiz["source"] = "assignment"
        return quiz

    @classmethod
    def _quiz(cls, quiz: dict[str, Any]) -> dict[str, Any]:
        shaped = cls._pick(
            quiz,
            "id",
            "title",
            "description",
            "quiz_type",
            "assignment_id",
            "due_at",
            "unlock_at",
            "lock_at",
            "time_limit",
            "allowed_attempts",
            "points_possible",
            "html_url",
            "published",
            "locked_for_user",
            "lock_explanation",
        )
        shaped["source"] = "classic_quiz"
        shaped["category"] = "quiz"
        shaped["deadline"] = quiz.get("due_at")
        return shaped

    @classmethod
    def _announcement(cls, announcement: dict[str, Any]) -> dict[str, Any]:
        shaped = cls._pick(
            announcement,
            "id",
            "title",
            "message",
            "posted_at",
            "delayed_post_at",
            "last_reply_at",
            "html_url",
            "context_code",
            "read_state",
            "unread_count",
            "published",
            "locked",
        )
        shaped["category"] = "announcement"
        return shaped

    @classmethod
    def _file(cls, file: dict[str, Any]) -> dict[str, Any]:
        shaped = cls._pick(
            file,
            "id",
            "display_name",
            "filename",
            "content-type",
            "content_type",
            "size",
            "created_at",
            "updated_at",
            "url",
            "locked_for_user",
            "lock_explanation",
        )
        shaped["category"] = cls._category(
            "File",
            str(file.get("display_name") or file.get("filename") or ""),
            "",
        )
        return shaped

    @classmethod
    def _categories(
        cls,
        modules: list[dict[str, Any]],
        assignments: list[dict[str, Any]],
        quizzes: list[dict[str, Any]],
        files: list[dict[str, Any]],
        announcements: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        categories = {key: [] for key in cls.CATEGORY_KEYS}
        category_keys = {
            "lecture": "lectures",
            "tutorial": "tutorials",
            "assignment": "assignments",
            "quiz": "quizzes",
            "discussion": "discussions",
            "reading": "readings",
            "announcement": "announcements",
            "other": "other",
        }
        seen: set[tuple[str, str]] = set()

        module_items: Iterable[dict[str, Any]] = (
            item
            for module in modules
            for item in module.get("items", [])
            if isinstance(item, dict)
        )
        for source, items in (
            ("module", module_items),
            ("assignment", assignments),
            ("quiz", quizzes),
            ("file", files),
            ("announcement", announcements),
        ):
            for item in items:
                identity = (source, str(item.get("id", "")))
                if identity in seen:
                    continue
                seen.add(identity)
                category = str(item.get("category", "other"))
                key = category_keys.get(category, "other")
                categories[key].append(
                    {
                        "source": source,
                        **cls._pick(
                            item,
                            "id",
                            "title",
                            "name",
                            "display_name",
                            "type",
                            "due_at",
                            "deadline",
                            "posted_at",
                            "html_url",
                            "url",
                        ),
                    }
                )
        return categories

    @classmethod
    def _deadlines(
        cls,
        modules: list[dict[str, Any]],
        assignments: list[dict[str, Any]],
        quizzes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        module_items: Iterable[dict[str, Any]] = (
            item
            for module in modules
            for item in module.get("items", [])
            if isinstance(item, dict)
        )
        deadlines: list[dict[str, Any]] = []
        for source, items in (
            ("module", module_items),
            ("assignment", assignments),
            ("quiz", quizzes),
        ):
            for item in items:
                deadline = item.get("deadline")
                if not isinstance(deadline, str) or not deadline:
                    continue
                deadlines.append(
                    {
                        "source": source,
                        "category": item.get("category", "other"),
                        **cls._pick(item, "id", "title", "name", "html_url", "url"),
                        "deadline": deadline,
                    }
                )
        deadlines.sort(key=cls._deadline_sort_key)
        return deadlines

    @staticmethod
    def _deadline_sort_key(item: dict[str, Any]) -> float:
        value = item.get("deadline")
        if not isinstance(value, str):
            return float("inf")
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return float("inf")

    @classmethod
    def _is_upcoming(cls, item: dict[str, Any]) -> bool:
        timestamp = cls._deadline_sort_key(item)
        return timestamp != float("inf") and timestamp >= datetime.now(UTC).timestamp()

    @staticmethod
    def _announcement_start(value: Any) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            start = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if start > datetime.now(UTC):
            return None
        return value

    @staticmethod
    def _category(item_type: str, title: str, module_name: str) -> str:
        normalized_type = item_type.casefold()
        if normalized_type == "assignment":
            return "assignment"
        if normalized_type == "quiz":
            return "quiz"
        if normalized_type == "discussion":
            return "discussion"

        text = f"{module_name} {title}".casefold()
        keyword_categories = (
            ("tutorial", r"\b(?:tutorial|tut|lab|workshop|practical)\b"),
            ("lecture", r"\b(?:lecture|lect|lec|slides?)\b"),
            ("reading", r"\b(?:reading|readings|textbook|chapter)\b"),
        )
        for category, pattern in keyword_categories:
            if re.search(pattern, text):
                return category
        return "other"

    @staticmethod
    def _pick(source: dict[str, Any], *keys: str) -> dict[str, Any]:
        return {key: source[key] for key in keys if key in source}
