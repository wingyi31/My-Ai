import asyncio

from app.services.canvas_reader import CanvasReadService


class FakeCanvasClient:
    async def get_current_user(self) -> dict:
        return {
            "id": "7",
            "name": "Student",
            "short_name": "Student",
            "login_id": "student@example.edu",
            "ignored": "value",
        }

    async def list_courses(self, *, include_completed: bool = False) -> list[dict]:
        assert include_completed is False
        return [{"id": "42", "name": "CS Course", "course_code": "CS0000"}]

    async def get_course(self, course_id: str | int) -> dict:
        assert str(course_id) == "42"
        return {"id": "42", "name": "CS Course", "course_code": "CS0000"}

    async def list_modules(self, course_id: str | int) -> list[dict]:
        return [
            {
                "id": "1",
                "name": "Week 1 Lecture",
                "position": 1,
                "items": [
                    {
                        "id": "11",
                        "title": "Introduction slides.pdf",
                        "type": "File",
                        "url": "https://canvas.example.edu/api/v1/files/11",
                    },
                    {
                        "id": "12",
                        "title": "Tutorial 1",
                        "type": "Page",
                        "content_details": {"due_at": "2026-08-28T10:00:00Z"},
                        "html_url": "https://canvas.example.edu/courses/42/pages/tutorial-1",
                    },
                ],
            }
        ]

    async def list_assignments(self, course_id: str | int) -> list[dict]:
        return [
            {
                "id": "21",
                "name": "Assignment 1",
                "due_at": "2026-09-01T10:00:00Z",
                "html_url": "https://canvas.example.edu/courses/42/assignments/21",
            },
            {
                "id": "26",
                "name": "Quiz 1",
                "is_quiz_assignment": True,
                "due_at": "2026-08-31T10:00:00Z",
                "html_url": "https://canvas.example.edu/courses/42/assignments/26",
            },
        ]

    async def list_quizzes(self, course_id: str | int) -> list[dict]:
        return [
            {
                "id": "25",
                "title": "Quiz 1",
                "assignment_id": "26",
                "due_at": "2026-08-30T10:00:00Z",
                "html_url": "https://canvas.example.edu/courses/42/quizzes/25",
            }
        ]

    async def list_announcements(
        self,
        course_id: str | int,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        assert end_date is not None
        return [
            {
                "id": "35",
                "title": "Welcome",
                "message": "Course starts this week",
                "posted_at": "2026-08-20T10:00:00Z",
                "context_code": "course_42",
            }
        ]

    async def list_files(self, course_id: str | int) -> list[dict]:
        return [
            {
                "id": "31",
                "display_name": "Required reading.pdf",
                "url": "https://canvas.example.edu/files/31/download",
            }
        ]


def test_canvas_reader_shapes_and_categorizes_course_content() -> None:
    async def run() -> None:
        service = CanvasReadService(FakeCanvasClient())  # type: ignore[arg-type]

        result = await service.course_content("42")

        assert result["access_mode"] == "read-only"
        assert result["course"]["course_code"] == "CS0000"
        assert result["modules"][0]["items"][0]["category"] == "lecture"
        assert result["modules"][0]["items"][1]["category"] == "tutorial"
        assert result["assignments"][0]["category"] == "assignment"
        assert result["assignments"][0]["deadline"] == "2026-09-01T10:00:00Z"
        assert result["quizzes"][0]["category"] == "quiz"
        assert result["quizzes"][0]["deadline"] == "2026-08-31T10:00:00Z"
        assert result["announcements"][0]["title"] == "Welcome"
        assert result["files"][0]["category"] == "reading"
        assert len(result["categories"]["lectures"]) == 1
        assert len(result["categories"]["tutorials"]) == 1
        assert len(result["categories"]["assignments"]) == 1
        assert len(result["categories"]["quizzes"]) == 1
        assert len(result["categories"]["announcements"]) == 1
        assert len(result["categories"]["readings"]) == 1
        assert [item["deadline"] for item in result["deadlines"]] == [
            "2026-08-28T10:00:00Z",
            "2026-08-31T10:00:00Z",
            "2026-09-01T10:00:00Z",
        ]
        assert result["upcoming_deadlines"] == result["deadlines"]
        assert result["warnings"] == []

    asyncio.run(run())


def test_canvas_reader_discovers_active_courses_before_loading_details() -> None:
    async def run() -> None:
        service = CanvasReadService(FakeCanvasClient())  # type: ignore[arg-type]

        result = await service.active_course_details()

        assert result["access_mode"] == "read-only"
        assert result["course_count"] == 1
        assert result["courses"][0]["course"]["id"] == "42"
        assert [item["deadline"] for item in result["deadlines"]] == [
            "2026-08-28T10:00:00Z",
            "2026-08-31T10:00:00Z",
            "2026-09-01T10:00:00Z",
        ]
        assert result["upcoming_deadlines"] == result["deadlines"]

    asyncio.run(run())
