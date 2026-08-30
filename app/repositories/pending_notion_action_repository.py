from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import (
    UTC,
    datetime,
    timedelta,
)

from google.cloud import firestore


PENDING_STATUS = "pending"
COMPLETED_STATUS = "completed"
CANCELLED_STATUS = "cancelled"
EXPIRED_STATUS = "expired"

PUBLISH_NOTION_SUMMARY_ACTION = (
    "publish_notion_summary"
)


class PendingNotionActionError(
    RuntimeError
):
    pass


class PendingNotionActionNotFoundError(
    PendingNotionActionError
):
    pass


class PendingNotionActionExpiredError(
    PendingNotionActionError
):
    pass


class PendingNotionActionStateError(
    PendingNotionActionError
):
    pass


@dataclass(frozen=True)
class PendingNotionAction:
    action_id: str
    user_id: str
    course_id: str
    session_id: str
    action_type: str
    summary_id: str
    title: str
    status: str
    created_at: datetime
    expires_at: datetime
    completed_at: datetime | None = None
    notion_page_id: str | None = None
    notion_page_url: str | None = None
    failed_attempts: int = 0
    last_error: str | None = None


class PendingNotionActionRepository:

    def __init__(
        self,
        db: firestore.AsyncClient,
    ) -> None:
        self._db = db

    @staticmethod
    def _clean_identifier(
        value: str,
        *,
        label: str,
    ) -> str:
        cleaned = str(value).strip()

        if not cleaned:
            raise ValueError(
                f"{label} cannot be empty"
            )

        if "/" in cleaned:
            raise ValueError(
                f"{label} cannot contain '/'"
            )

        return cleaned

    def _action_ref(
        self,
        *,
        user_id: str,
        action_id: str,
    ):
        return (
            self._db
            .collection("users")
            .document(user_id)
            .collection(
                "pending_notion_actions"
            )
            .document(action_id)
        )

    async def create_publish_action(
        self,
        *,
        user_id: str,
        course_id: str,
        session_id: str,
        summary_id: str,
        title: str,
        expires_in_minutes: int = 30,
    ) -> PendingNotionAction:
        cleaned_user_id = (
            self._clean_identifier(
                user_id,
                label="User ID",
            )
        )
        cleaned_course_id = (
            self._clean_identifier(
                course_id,
                label="Course ID",
            )
        )
        cleaned_session_id = (
            self._clean_identifier(
                session_id,
                label="Session ID",
            )
        )
        cleaned_summary_id = (
            self._clean_identifier(
                summary_id,
                label="Summary ID",
            )
        )
        cleaned_title = title.strip()

        if not cleaned_title:
            raise ValueError(
                "Notion page title cannot be empty"
            )

        if len(cleaned_title) > 200:
            raise ValueError(
                "Notion page title cannot exceed "
                "200 characters"
            )

        if not 1 <= expires_in_minutes <= 60:
            raise ValueError(
                "Pending action expiry must be "
                "between 1 and 60 minutes"
            )

        action_id = secrets.token_urlsafe(
            24
        )
        created_at = datetime.now(UTC)
        expires_at = (
            created_at
            + timedelta(
                minutes=expires_in_minutes
            )
        )

        action = PendingNotionAction(
            action_id=action_id,
            user_id=cleaned_user_id,
            course_id=cleaned_course_id,
            session_id=cleaned_session_id,
            action_type=(
                PUBLISH_NOTION_SUMMARY_ACTION
            ),
            summary_id=cleaned_summary_id,
            title=cleaned_title,
            status=PENDING_STATUS,
            created_at=created_at,
            expires_at=expires_at,
        )

        await self._action_ref(
            user_id=cleaned_user_id,
            action_id=action_id,
        ).create(
            {
                "action_id": action.action_id,
                "user_id": action.user_id,
                "course_id": action.course_id,
                "session_id": (
                    action.session_id
                ),
                "action_type": (
                    action.action_type
                ),
                "summary_id": (
                    action.summary_id
                ),
                "title": action.title,
                "status": action.status,
                "created_at": (
                    action.created_at
                ),
                "expires_at": (
                    action.expires_at
                ),
                "completed_at": None,
                "notion_page_id": None,
                "notion_page_url": None,
                "failed_attempts": 0,
                "last_error": None,
                "last_failed_at": None,
            }
        )

        return action

    async def get_action(
        self,
        *,
        user_id: str,
        action_id: str,
    ) -> PendingNotionAction:
        cleaned_user_id = (
            self._clean_identifier(
                user_id,
                label="User ID",
            )
        )
        cleaned_action_id = (
            self._clean_identifier(
                action_id,
                label="Action ID",
            )
        )

        snapshot = await self._action_ref(
            user_id=cleaned_user_id,
            action_id=cleaned_action_id,
        ).get()

        if not snapshot.exists:
            raise (
                PendingNotionActionNotFoundError(
                    "Pending Notion action was not "
                    "found"
                )
            )

        data = snapshot.to_dict()

        if not isinstance(data, dict):
            raise PendingNotionActionError(
                "Pending Notion action contains "
                "invalid data"
            )

        return self._deserialize(data)

    async def get_confirmable_action(
        self,
        *,
        user_id: str,
        action_id: str,
    ) -> PendingNotionAction:
        action = await self.get_action(
            user_id=user_id,
            action_id=action_id,
        )

        if action.status != PENDING_STATUS:
            raise PendingNotionActionStateError(
                "Action cannot be confirmed because "
                f"its status is {action.status}"
            )

        if action.expires_at <= datetime.now(UTC):
            await self._action_ref(
                user_id=action.user_id,
                action_id=action.action_id,
            ).set(
                {
                    "status": EXPIRED_STATUS,
                    "expired_at": (
                        firestore.SERVER_TIMESTAMP
                    ),
                },
                merge=True,
            )

            raise PendingNotionActionExpiredError(
                "Pending Notion action has expired"
            )

        return action

    async def mark_completed(
        self,
        *,
        user_id: str,
        action_id: str,
        notion_page_id: str,
        notion_page_url: str,
    ) -> None:
        cleaned_page_id = (
            self._clean_identifier(
                notion_page_id,
                label="Notion page ID",
            )
        )
        cleaned_page_url = (
            notion_page_url.strip()
        )

        if not cleaned_page_url:
            raise ValueError(
                "Notion page URL cannot be empty"
            )

        await self._action_ref(
            user_id=self._clean_identifier(
                user_id,
                label="User ID",
            ),
            action_id=self._clean_identifier(
                action_id,
                label="Action ID",
            ),
        ).set(
            {
                "status": COMPLETED_STATUS,
                "completed_at": (
                    firestore.SERVER_TIMESTAMP
                ),
                "notion_page_id": (
                    cleaned_page_id
                ),
                "notion_page_url": (
                    cleaned_page_url
                ),
                "last_error": None,
            },
            merge=True,
        )

    async def record_failure(
        self,
        *,
        user_id: str,
        action_id: str,
        error_message: str,
    ) -> None:
        action = await self.get_action(
            user_id=user_id,
            action_id=action_id,
        )

        if action.status != PENDING_STATUS:
            raise PendingNotionActionStateError(
                "Only a pending action can record "
                "a publishing failure"
            )

        cleaned_error = (
            error_message.strip()
            or "Unknown Notion publishing error"
        )[:500]

        await self._action_ref(
            user_id=action.user_id,
            action_id=action.action_id,
        ).set(
            {
                "failed_attempts": (
                    firestore.Increment(1)
                ),
                "last_error": cleaned_error,
                "last_failed_at": (
                    firestore.SERVER_TIMESTAMP
                ),
            },
            merge=True,
        )

    async def cancel_action(
        self,
        *,
        user_id: str,
        action_id: str,
    ) -> None:
        action = await self.get_action(
            user_id=user_id,
            action_id=action_id,
        )

        if action.status != PENDING_STATUS:
            raise PendingNotionActionStateError(
                "Only a pending action can be "
                "cancelled"
            )

        await self._action_ref(
            user_id=action.user_id,
            action_id=action.action_id,
        ).set(
            {
                "status": CANCELLED_STATUS,
                "cancelled_at": (
                    firestore.SERVER_TIMESTAMP
                ),
            },
            merge=True,
        )

    @staticmethod
    def _deserialize(
        data: dict,
    ) -> PendingNotionAction:
        required_strings = (
            "action_id",
            "user_id",
            "course_id",
            "session_id",
            "action_type",
            "summary_id",
            "title",
            "status",
        )

        values: dict[str, str] = {}

        for field in required_strings:
            value = data.get(field)

            if (
                not isinstance(value, str)
                or not value
            ):
                raise PendingNotionActionError(
                    "Pending Notion action is "
                    f"missing {field}"
                )

            values[field] = value

        if (
            values["action_type"]
            != PUBLISH_NOTION_SUMMARY_ACTION
        ):
            raise PendingNotionActionError(
                "Pending Notion action type is "
                "invalid"
            )

        created_at = data.get("created_at")
        expires_at = data.get("expires_at")

        if not isinstance(
            created_at,
            datetime,
        ):
            raise PendingNotionActionError(
                "Pending Notion action creation "
                "time is invalid"
            )

        if not isinstance(
            expires_at,
            datetime,
        ):
            raise PendingNotionActionError(
                "Pending Notion action expiry is "
                "invalid"
            )

        completed_at = data.get(
            "completed_at"
        )

        if not isinstance(
            completed_at,
            datetime,
        ):
            completed_at = None

        notion_page_id = data.get(
            "notion_page_id"
        )
        notion_page_url = data.get(
            "notion_page_url"
        )
        last_error = data.get("last_error")
        failed_attempts = data.get(
            "failed_attempts",
            0,
        )

        if not isinstance(failed_attempts, int):
            failed_attempts = 0

        return PendingNotionAction(
            action_id=values["action_id"],
            user_id=values["user_id"],
            course_id=values["course_id"],
            session_id=values["session_id"],
            action_type=values["action_type"],
            summary_id=values["summary_id"],
            title=values["title"],
            status=values["status"],
            created_at=created_at,
            expires_at=expires_at,
            completed_at=completed_at,
            notion_page_id=(
                notion_page_id
                if isinstance(
                    notion_page_id,
                    str,
                )
                else None
            ),
            notion_page_url=(
                notion_page_url
                if isinstance(
                    notion_page_url,
                    str,
                )
                else None
            ),
            failed_attempts=max(
                failed_attempts,
                0,
            ),
            last_error=(
                last_error
                if isinstance(last_error, str)
                else None
            ),
        )