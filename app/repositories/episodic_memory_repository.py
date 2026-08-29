from __future__ import annotations

import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from google.cloud import firestore


EVENT_TYPE_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*"
    r"(?:\.[a-z][a-z0-9_]*)+$"
)


@dataclass(frozen=True)
class EpisodicEvent:
    event_id: str
    event_type: str
    user_id: str
    course_id: str
    occurred_at: datetime
    payload: dict[str, Any]
    session_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None


class EpisodicMemoryRepository:

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

    @classmethod
    def _clean_optional_identifier(
        cls,
        value: str | None,
        *,
        label: str,
    ) -> str | None:
        if value is None:
            return None

        return cls._clean_identifier(
            value,
            label=label,
        )

    def _events_ref(
        self,
        *,
        user_id: str,
    ):
        return (
            self._db
            .collection("users")
            .document(user_id)
            .collection("episodes")
        )

    async def record_event(
        self,
        *,
        user_id: str,
        course_id: str,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        session_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> EpisodicEvent:
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
        cleaned_event_type = str(
            event_type
        ).strip()

        if not EVENT_TYPE_PATTERN.fullmatch(
            cleaned_event_type
        ):
            raise ValueError(
                "Event type must use dot-separated "
                "lowercase names"
            )

        cleaned_session_id = (
            self._clean_optional_identifier(
                session_id,
                label="Session ID",
            )
        )
        cleaned_entity_type = (
            self._clean_optional_identifier(
                entity_type,
                label="Entity type",
            )
        )
        cleaned_entity_id = (
            self._clean_optional_identifier(
                entity_id,
                label="Entity ID",
            )
        )

        if (
            cleaned_entity_type is None
            and cleaned_entity_id is not None
        ):
            raise ValueError(
                "Entity type is required when "
                "entity ID is provided"
            )

        event_id = secrets.token_urlsafe(18)
        occurred_at = datetime.now(UTC)
        event_payload = dict(payload or {})

        event = EpisodicEvent(
            event_id=event_id,
            event_type=cleaned_event_type,
            user_id=cleaned_user_id,
            course_id=cleaned_course_id,
            session_id=cleaned_session_id,
            entity_type=cleaned_entity_type,
            entity_id=cleaned_entity_id,
            occurred_at=occurred_at,
            payload=event_payload,
        )

        event_ref = (
            self._events_ref(
                user_id=cleaned_user_id
            )
            .document(event_id)
        )

        # Firestore create() fails if the document
        # already exists, preserving append-only
        # event semantics.
        await event_ref.create(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "user_id": event.user_id,
                "course_id": event.course_id,
                "session_id": event.session_id,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "occurred_at": event.occurred_at,
                "payload": event.payload,
            }
        )

        return event

    async def list_recent_events(
        self,
        *,
        user_id: str,
        course_id: str,
        limit: int = 20,
    ) -> tuple[EpisodicEvent, ...]:
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

        if not 1 <= limit <= 100:
            raise ValueError(
                "Event limit must be between "
                "1 and 100"
            )

        events: list[EpisodicEvent] = []

        async for snapshot in (
            self._events_ref(
                user_id=cleaned_user_id
            ).stream()
        ):
            data = snapshot.to_dict() or {}

            if (
                str(data.get("course_id", ""))
                != cleaned_course_id
            ):
                continue

            event_id = data.get("event_id")
            event_type = data.get("event_type")
            occurred_at = data.get(
                "occurred_at"
            )
            payload = data.get("payload")

            if (
                not isinstance(event_id, str)
                or not event_id
                or not isinstance(
                    event_type,
                    str,
                )
                or not isinstance(
                    occurred_at,
                    datetime,
                )
                or not isinstance(payload, dict)
            ):
                continue

            events.append(
                EpisodicEvent(
                    event_id=event_id,
                    event_type=event_type,
                    user_id=cleaned_user_id,
                    course_id=cleaned_course_id,
                    session_id=(
                        data.get("session_id")
                        if isinstance(
                            data.get("session_id"),
                            str,
                        )
                        else None
                    ),
                    entity_type=(
                        data.get("entity_type")
                        if isinstance(
                            data.get("entity_type"),
                            str,
                        )
                        else None
                    ),
                    entity_id=(
                        data.get("entity_id")
                        if isinstance(
                            data.get("entity_id"),
                            str,
                        )
                        else None
                    ),
                    occurred_at=occurred_at,
                    payload=payload,
                )
            )

        events.sort(
            key=lambda event: event.occurred_at,
            reverse=True,
        )

        return tuple(events[:limit])