from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from typing import Any

from google.cloud import firestore


PENDING_STATUS = "pending"
COMPLETED_STATUS = "completed"
CANCELLED_STATUS = "cancelled"
EXPIRED_STATUS = "expired"

CREATE_CALENDAR_EVENT_ACTION = (
    "create_calendar_event"
)


class PendingActionError(RuntimeError):
    pass


class PendingActionNotFoundError(
    PendingActionError
):
    pass


class PendingActionExpiredError(
    PendingActionError
):
    pass


class PendingActionStateError(
    PendingActionError
):
    pass


@dataclass(frozen=True)
class PendingCalendarAction:
    action_id: str
    user_id: str
    course_id: str
    action_type: str
    status: str
    event_id: str
    event: dict[str, Any]
    source: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    idempotency_key: str | None = None
    completed_at: datetime | None = None
    calendar_event_id: str | None = None
    calendar_event_link: str | None = None


class PendingActionRepository:

    def __init__(
        self,
        db: firestore.AsyncClient,
    ) -> None:
        self._db = db

    def _action_ref(
        self,
        *,
        user_id: str,
        action_id: str,
    ):
        return (
            self._db
            .collection("users")
            .document(str(user_id))
            .collection("pending_actions")
            .document(str(action_id))
        )

    async def create_calendar_event_action(
        self,
        *,
        user_id: str,
        course_id: str,
        event: Mapping[str, Any],
        source: Mapping[str, Any],
        idempotency_key: str | None = None,
        expires_in_minutes: int = 15,
    ) -> PendingCalendarAction:
        cleaned_user_id = str(
            user_id
        ).strip()
        cleaned_course_id = str(
            course_id
        ).strip()

        if not cleaned_user_id:
            raise ValueError(
                "User ID cannot be empty"
            )

        if not cleaned_course_id:
            raise ValueError(
                "Course ID cannot be empty"
            )

        if not 1 <= expires_in_minutes <= 60:
            raise ValueError(
                "Pending action expiry must be "
                "between 1 and 60 minutes"
            )

        event_data = dict(event)
        source_data = dict(source)

        if not event_data:
            raise ValueError(
                "Calendar event cannot be empty"
            )

        cleaned_idempotency_key = (
            idempotency_key.strip()
            if idempotency_key is not None
            else None
        )

        if (
            idempotency_key is not None
            and not cleaned_idempotency_key
        ):
            raise ValueError(
                "Idempotency key cannot be empty"
            )

        action_id = secrets.token_urlsafe(
            24
        )

        # When an idempotency key is supplied,
        # separate proposals for the same Canvas
        # item produce the same Calendar event ID.
        #
        # When no key is supplied, the action ID
        # keeps the event unique.
        event_identity = (
            cleaned_idempotency_key
            or action_id
        )

        # Hexadecimal characters are a valid subset
        # of Google Calendar's base32hex event-ID
        # characters.
        event_id = hashlib.sha256(
            (
                f"{cleaned_user_id}:"
                f"{event_identity}"
            ).encode("utf-8")
        ).hexdigest()[:32]

        created_at = datetime.now(UTC)
        expires_at = (
            created_at
            + timedelta(
                minutes=expires_in_minutes
            )
        )

        action = PendingCalendarAction(
            action_id=action_id,
            user_id=cleaned_user_id,
            course_id=cleaned_course_id,
            action_type=(
                CREATE_CALENDAR_EVENT_ACTION
            ),
            status=PENDING_STATUS,
            event_id=event_id,
            event=event_data,
            source=source_data,
            created_at=created_at,
            expires_at=expires_at,
            idempotency_key=(
                cleaned_idempotency_key
            ),
        )

        await self._action_ref(
            user_id=cleaned_user_id,
            action_id=action_id,
        ).set(
            {
                "action_id": action.action_id,
                "user_id": action.user_id,
                "course_id": action.course_id,
                "action_type": (
                    action.action_type
                ),
                "status": action.status,
                "event_id": action.event_id,
                "idempotency_key": (
                    action.idempotency_key
                ),
                "event": action.event,
                "source": action.source,
                "created_at": (
                    action.created_at
                ),
                "expires_at": (
                    action.expires_at
                ),
                "completed_at": None,
                "calendar_event_id": None,
                "calendar_event_link": None,
            }
        )

        return action

    async def get_action(
        self,
        *,
        user_id: str,
        action_id: str,
    ) -> PendingCalendarAction:
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

        snapshot = await self._action_ref(
            user_id=cleaned_user_id,
            action_id=cleaned_action_id,
        ).get()

        if not snapshot.exists:
            raise PendingActionNotFoundError(
                "Pending action was not found"
            )

        data = snapshot.to_dict()

        if not isinstance(data, dict):
            raise PendingActionError(
                "Pending action contains invalid "
                "data"
            )

        return self._deserialize(data)

    async def get_confirmable_action(
        self,
        *,
        user_id: str,
        action_id: str,
    ) -> PendingCalendarAction:
        action = await self.get_action(
            user_id=user_id,
            action_id=action_id,
        )

        if action.status != PENDING_STATUS:
            raise PendingActionStateError(
                "Action cannot be confirmed because "
                f"its status is {action.status}"
            )

        if (
            action.expires_at
            <= datetime.now(UTC)
        ):
            await self._action_ref(
                user_id=user_id,
                action_id=action_id,
            ).set(
                {
                    "status": EXPIRED_STATUS,
                    "expired_at": (
                        firestore.SERVER_TIMESTAMP
                    ),
                },
                merge=True,
            )

            raise PendingActionExpiredError(
                "Pending action has expired"
            )

        return action

    async def mark_completed(
        self,
        *,
        user_id: str,
        action_id: str,
        calendar_event_id: str,
        calendar_event_link: str | None,
    ) -> None:
        cleaned_calendar_event_id = (
            calendar_event_id.strip()
        )

        if not cleaned_calendar_event_id:
            raise ValueError(
                "Calendar event ID cannot be empty"
            )

        await self._action_ref(
            user_id=user_id,
            action_id=action_id,
        ).set(
            {
                "status": COMPLETED_STATUS,
                "completed_at": (
                    firestore.SERVER_TIMESTAMP
                ),
                "calendar_event_id": (
                    cleaned_calendar_event_id
                ),
                "calendar_event_link": (
                    calendar_event_link
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
            raise PendingActionStateError(
                "Only a pending action can be "
                "cancelled"
            )

        await self._action_ref(
            user_id=user_id,
            action_id=action_id,
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
        data: dict[str, Any],
    ) -> PendingCalendarAction:
        required_strings = (
            "action_id",
            "user_id",
            "course_id",
            "action_type",
            "status",
            "event_id",
        )

        values: dict[str, str] = {}

        for field in required_strings:
            value = data.get(field)

            if (
                not isinstance(value, str)
                or not value
            ):
                raise PendingActionError(
                    "Pending action is missing "
                    f"{field}"
                )

            values[field] = value

        event = data.get("event")
        source = data.get("source")
        created_at = data.get("created_at")
        expires_at = data.get("expires_at")

        if not isinstance(event, dict):
            raise PendingActionError(
                "Pending action event is invalid"
            )

        if not isinstance(source, dict):
            raise PendingActionError(
                "Pending action source is invalid"
            )

        if not isinstance(
            created_at,
            datetime,
        ):
            raise PendingActionError(
                "Pending action creation time is "
                "invalid"
            )

        if not isinstance(
            expires_at,
            datetime,
        ):
            raise PendingActionError(
                "Pending action expiry is invalid"
            )

        idempotency_key = data.get(
            "idempotency_key"
        )

        if not isinstance(
            idempotency_key,
            str,
        ):
            idempotency_key = None

        completed_at = data.get(
            "completed_at"
        )

        if not isinstance(
            completed_at,
            datetime,
        ):
            completed_at = None

        calendar_event_id = data.get(
            "calendar_event_id"
        )

        if not isinstance(
            calendar_event_id,
            str,
        ):
            calendar_event_id = None

        calendar_event_link = data.get(
            "calendar_event_link"
        )

        if not isinstance(
            calendar_event_link,
            str,
        ):
            calendar_event_link = None

        return PendingCalendarAction(
            action_id=values["action_id"],
            user_id=values["user_id"],
            course_id=values["course_id"],
            action_type=(
                values["action_type"]
            ),
            status=values["status"],
            event_id=values["event_id"],
            event=dict(event),
            source=dict(source),
            created_at=created_at,
            expires_at=expires_at,
            idempotency_key=(
                idempotency_key
            ),
            completed_at=completed_at,
            calendar_event_id=(
                calendar_event_id
            ),
            calendar_event_link=(
                calendar_event_link
            ),
        )