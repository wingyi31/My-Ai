from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from google.cloud import firestore



ConversationRole = Literal[
    "user",
    "assistant",
]

SESSION_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{1,200}$"
)


class ConversationError(ValueError):
    pass


class ConversationSessionMismatchError(
    ConversationError
):
    pass


@dataclass(frozen=True)
class ConversationMessage:
    role: ConversationRole
    content: str
    created_at: datetime

@dataclass(frozen=True)
class ConversationSummary:
    session_id: str
    course_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationRepository:

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
    def _clean_session_id(
        cls,
        session_id: str,
    ) -> str:
        cleaned = cls._clean_identifier(
            session_id,
            label="Session ID",
        )

        if not SESSION_ID_PATTERN.fullmatch(
            cleaned
        ):
            raise ValueError(
                "Session ID may contain only "
                "letters, numbers, underscores, "
                "and hyphens"
            )

        return cleaned

    def _conversation_ref(
        self,
        *,
        user_id: str,
        session_id: str,
    ):
        return (
            self._db
            .collection("users")
            .document(user_id)
            .collection("conversations")
            .document(session_id)
        )

    async def list_conversations(
        self,
        *,
        user_id: str,
        course_id: str,
        limit: int = 20,
    ) -> tuple[ConversationSummary, ...]:
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

        if not 1 <= limit <= 50:
            raise ValueError(
                "Conversation limit must be "
                "between 1 and 50"
            )

        conversations_ref = (
            self._db
            .collection("users")
            .document(cleaned_user_id)
            .collection("conversations")
        )

        conversations: list[
            ConversationSummary
        ] = []

        async for snapshot in (
            conversations_ref.stream()
        ):
            data = snapshot.to_dict() or {}

            stored_course_id = str(
                data.get("course_id", "")
            )

            if (
                stored_course_id
                != cleaned_course_id
            ):
                continue

            session_id = str(
                data.get(
                    "session_id",
                    snapshot.id,
                )
            )

            if not SESSION_ID_PATTERN.fullmatch(
                session_id
            ):
                continue

            created_at = data.get("created_at")
            updated_at = data.get("updated_at")

            if not isinstance(
                updated_at,
                datetime,
            ):
                continue

            if not isinstance(
                created_at,
                datetime,
            ):
                created_at = updated_at

            raw_title = data.get("title")
            title = (
                raw_title.strip()
                if isinstance(raw_title, str)
                and raw_title.strip()
                else "New conversation"
            )

            conversations.append(
                ConversationSummary(
                    session_id=session_id,
                    course_id=stored_course_id,
                    title=title,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )

        conversations.sort(
            key=lambda item: item.updated_at,
            reverse=True,
        )

        return tuple(
            conversations[:limit]
        )

    async def load_recent_messages(
        self,
        *,
        user_id: str,
        course_id: str,
        session_id: str,
        limit: int = 10,
    ) -> tuple[ConversationMessage, ...]:
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
            self._clean_session_id(session_id)
        )

        if not 1 <= limit <= 100:
            raise ValueError(
                "History limit must be between "
                "1 and 100"
            )

        conversation_ref = (
            self._conversation_ref(
                user_id=cleaned_user_id,
                session_id=cleaned_session_id,
            )
        )
        conversation_snapshot = (
            await conversation_ref.get()
        )

        if not conversation_snapshot.exists:
            return ()

        conversation_data = (
            conversation_snapshot.to_dict()
            or {}
        )
        stored_course_id = str(
            conversation_data.get(
                "course_id",
                "",
            )
        )

        if stored_course_id != cleaned_course_id:
            raise (
                ConversationSessionMismatchError(
                    "Conversation belongs to a "
                    "different course"
                )
            )

        query = (
            conversation_ref
            .collection("messages")
            .order_by(
                "created_at",
                direction=(
                    firestore.Query.DESCENDING
                ),
            )
            .limit(limit)
        )

        messages: list[
            ConversationMessage
        ] = []

        async for snapshot in query.stream():
            data = snapshot.to_dict() or {}
            role = data.get("role")
            content = data.get("content")
            created_at = data.get(
                "created_at"
            )

            if role not in {
                "user",
                "assistant",
            }:
                continue

            if (
                not isinstance(content, str)
                or not content.strip()
            ):
                continue

            if not isinstance(
                created_at,
                datetime,
            ):
                continue

            messages.append(
                ConversationMessage(
                    role=role,
                    content=content,
                    created_at=created_at,
                )
            )

        messages.reverse()
        return tuple(messages)

    async def append_turn(
        self,
        *,
        user_id: str,
        course_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
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
            self._clean_session_id(session_id)
        )
        cleaned_user_message = (
            user_message.strip()
        )
        cleaned_assistant_message = (
            assistant_message.strip()
        )

        if not cleaned_user_message:
            raise ValueError(
                "User message cannot be empty"
            )

        if not cleaned_assistant_message:
            raise ValueError(
                "Assistant message cannot be "
                "empty"
            )

        conversation_ref = (
            self._conversation_ref(
                user_id=cleaned_user_id,
                session_id=cleaned_session_id,
            )
        )
        conversation_snapshot = (
            await conversation_ref.get()
        )
        conversation_data = (
            conversation_snapshot.to_dict()
            or {}
        )

        if conversation_snapshot.exists:
            stored_course_id = str(
                conversation_data.get(
                    "course_id",
                    "",
                )
            )

            if (
                stored_course_id
                != cleaned_course_id
            ):
                raise (
                    ConversationSessionMismatchError(
                        "Conversation belongs to "
                        "a different course"
                    )
                )

        turn_id = secrets.token_urlsafe(18)
        user_created_at = datetime.now(UTC)
        assistant_created_at = (
            user_created_at
            + timedelta(microseconds=1)
        )

        conversation_values = {
            "session_id": cleaned_session_id,
            "user_id": cleaned_user_id,
            "course_id": cleaned_course_id,
            "updated_at": assistant_created_at,
        }

        if not conversation_snapshot.exists:
            conversation_values[
                "created_at"
            ] = user_created_at
            conversation_values["title"] = (
                " ".join(
                    cleaned_user_message.split()
                )[:80]
            )

        messages_ref = (
            conversation_ref.collection(
                "messages"
            )
        )
        batch = self._db.batch()

        batch.set(
            conversation_ref,
            conversation_values,
            merge=True,
        )
        batch.set(
            messages_ref.document(
                f"{turn_id}_user"
            ),
            {
                "turn_id": turn_id,
                "role": "user",
                "content": (
                    cleaned_user_message
                ),
                "created_at": user_created_at,
            },
        )
        batch.set(
            messages_ref.document(
                f"{turn_id}_assistant"
            ),
            {
                "turn_id": turn_id,
                "role": "assistant",
                "content": (
                    cleaned_assistant_message
                ),
                "created_at": (
                    assistant_created_at
                ),
            },
        )

        await batch.commit()