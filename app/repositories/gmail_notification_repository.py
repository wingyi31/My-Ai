from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from google.api_core.exceptions import (
    AlreadyExists,
)
from google.cloud import firestore

from app.connectors.gmail.parser import (
    ParsedEmail,
)


GmailRelevance = Literal[
    "canvas",
    "academic",
    "campus",
    "unrelated",
]

MAX_SUBJECT_LENGTH = 500
MAX_SNIPPET_LENGTH = 2000
MAX_BODY_LENGTH = 12000
MAX_ATTACHMENT_NAMES = 20


class GmailNotificationError(RuntimeError):
    pass


class GmailNotificationNotFoundError(
    GmailNotificationError
):
    pass


@dataclass(frozen=True)
class GmailNotification:
    user_id: str
    message_id: str
    thread_id: str | None
    history_id: str | None
    subject: str
    from_address: str | None
    sent_at: datetime | None
    internal_date: datetime | None
    snippet: str
    text_body: str | None
    labels: tuple[str, ...]
    attachment_names: tuple[str, ...]
    relevance: GmailRelevance
    is_relevant: bool
    published: bool
    notion_page_id: str | None
    notion_page_url: str | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class GmailNotificationRepository:

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

    def _notifications_ref(
        self,
        *,
        user_id: str,
    ):
        return (
            self._db
            .collection("users")
            .document(user_id)
            .collection("gmail_notifications")
        )

    def _notification_ref(
        self,
        *,
        user_id: str,
        message_id: str,
    ):
        return (
            self._notifications_ref(
                user_id=user_id
            )
            .document(message_id)
        )

    def _state_ref(
        self,
        *,
        user_id: str,
    ):
        return (
            self._db
            .collection("users")
            .document(user_id)
            .collection("integration_state")
            .document("gmail")
        )

    async def persist_email(
        self,
        *,
        user_id: str,
        email: ParsedEmail,
    ) -> GmailNotification:
        cleaned_user_id = (
            self._clean_identifier(
                user_id,
                label="User ID",
            )
        )
        cleaned_message_id = (
            self._clean_identifier(
                email.message_id,
                label="Gmail message ID",
            )
        )

        now = datetime.now(UTC)
        subject = self._truncate(
            email.subject,
            MAX_SUBJECT_LENGTH,
        )
        snippet = self._truncate(
            email.snippet,
            MAX_SNIPPET_LENGTH,
        )
        text_body = self._optional_truncate(
            email.text_body,
            MAX_BODY_LENGTH,
        )

        relevance = self._classify_relevance(
            subject=subject,
            from_address=email.from_address,
            snippet=snippet,
            text_body=text_body,
        )

        attachment_names = [
            self._truncate(
                attachment.filename,
                300,
            )
            for attachment
            in email.attachments[
                :MAX_ATTACHMENT_NAMES
            ]
        ]

        stable_payload: dict[str, Any] = {
            "user_id": cleaned_user_id,
            "message_id": cleaned_message_id,
            "thread_id": email.thread_id,
            "history_id": email.history_id,
            "subject": subject,
            "from_address": (
                email.from_address
            ),
            "sent_at": email.sent_at,
            "internal_date": (
                email.internal_date
            ),
            "snippet": snippet,
            "text_body": text_body,
            "labels": list(email.labels),
            "attachment_names": (
                attachment_names
            ),
            "attachment_count": len(
                email.attachments
            ),
            "relevance": relevance,
            "is_relevant": (
                relevance != "unrelated"
            ),
            "updated_at": now,
        }

        initial_payload = {
            **stable_payload,
            "published": False,
            "notion_page_id": None,
            "notion_page_url": None,
            "published_at": None,
            "created_at": now,
        }

        notification_ref = (
            self._notification_ref(
                user_id=cleaned_user_id,
                message_id=cleaned_message_id,
            )
        )

        try:
            await notification_ref.create(
                initial_payload
            )
        except AlreadyExists:
            # Reprocessing the same Gmail message
            # refreshes its parsed fields without
            # resetting publication state.
            await notification_ref.set(
                stable_payload,
                merge=True,
            )

        snapshot = await notification_ref.get()
        data = snapshot.to_dict()

        if not isinstance(data, dict):
            raise GmailNotificationError(
                "Persisted Gmail notification "
                "contains invalid data"
            )

        return self._deserialize(data)

    async def list_unpublished_relevant(
        self,
        *,
        user_id: str,
        limit: int = 50,
    ) -> tuple[GmailNotification, ...]:
        cleaned_user_id = (
            self._clean_identifier(
                user_id,
                label="User ID",
            )
        )

        if not 1 <= limit <= 200:
            raise ValueError(
                "Notification limit must be "
                "between 1 and 200"
            )

        notifications: list[
            GmailNotification
        ] = []

        async for snapshot in (
            self._notifications_ref(
                user_id=cleaned_user_id
            ).stream()
        ):
            data = snapshot.to_dict()

            if not isinstance(data, dict):
                continue

            if data.get("is_relevant") is not True:
                continue

            if data.get("published") is not False:
                continue

            try:
                notification = (
                    self._deserialize(data)
                )
            except GmailNotificationError:
                continue

            notifications.append(notification)

        notifications.sort(
            key=self._notification_sort_key,
        )

        return tuple(
            notifications[:limit]
        )

    async def mark_published(
        self,
        *,
        user_id: str,
        message_ids: (
            list[str] | tuple[str, ...]
        ),
        notion_page_id: str,
        notion_page_url: str,
    ) -> None:
        cleaned_user_id = (
            self._clean_identifier(
                user_id,
                label="User ID",
            )
        )
        cleaned_page_id = (
            self._clean_identifier(
                notion_page_id,
                label="Notion page ID",
            )
        )
        cleaned_page_url = str(
            notion_page_url
        ).strip()

        if not cleaned_page_url:
            raise ValueError(
                "Notion page URL cannot be empty"
            )

        cleaned_message_ids = tuple(
            self._clean_identifier(
                message_id,
                label="Gmail message ID",
            )
            for message_id in message_ids
        )

        if not cleaned_message_ids:
            raise ValueError(
                "At least one Gmail message ID "
                "is required"
            )

        published_at = datetime.now(UTC)

        for message_id in dict.fromkeys(
            cleaned_message_ids
        ):
            notification_ref = (
                self._notification_ref(
                    user_id=cleaned_user_id,
                    message_id=message_id,
                )
            )
            snapshot = (
                await notification_ref.get()
            )

            if not snapshot.exists:
                raise (
                    GmailNotificationNotFoundError(
                        "Gmail notification was "
                        f"not found: {message_id}"
                    )
                )

            await notification_ref.set(
                {
                    "published": True,
                    "published_at": (
                        published_at
                    ),
                    "notion_page_id": (
                        cleaned_page_id
                    ),
                    "notion_page_url": (
                        cleaned_page_url
                    ),
                    "updated_at": (
                        published_at
                    ),
                },
                merge=True,
            )

    async def load_history_id(
        self,
        *,
        user_id: str,
    ) -> str | None:
        cleaned_user_id = (
            self._clean_identifier(
                user_id,
                label="User ID",
            )
        )

        snapshot = await self._state_ref(
            user_id=cleaned_user_id
        ).get()

        if not snapshot.exists:
            return None

        data = snapshot.to_dict()

        if not isinstance(data, dict):
            raise GmailNotificationError(
                "Gmail integration state is "
                "invalid"
            )

        history_id = data.get("history_id")

        if (
            not isinstance(history_id, str)
            or not history_id
        ):
            raise GmailNotificationError(
                "Gmail integration state has no "
                "history ID"
            )

        return history_id

    async def save_history_id(
        self,
        *,
        user_id: str,
        history_id: str,
        account_email: str | None = None,
    ) -> None:
        cleaned_user_id = (
            self._clean_identifier(
                user_id,
                label="User ID",
            )
        )
        cleaned_history_id = str(
            history_id
        ).strip()

        if not cleaned_history_id:
            raise ValueError(
                "Gmail history ID cannot be empty"
            )

        cleaned_account_email = (
            str(account_email).strip()
            if account_email is not None
            else None
        )

        await self._state_ref(
            user_id=cleaned_user_id
        ).set(
            {
                "user_id": cleaned_user_id,
                "history_id": (
                    cleaned_history_id
                ),
                "account_email": (
                    cleaned_account_email
                ),
                "updated_at": (
                    datetime.now(UTC)
                ),
            },
            merge=True,
        )

    @staticmethod
    def _classify_relevance(
        *,
        subject: str,
        from_address: str | None,
        snippet: str,
        text_body: str | None,
    ) -> GmailRelevance:
        sender = (
            from_address or ""
        ).casefold()
        subject_text = subject.casefold()
        content = " ".join(
            [
                subject_text,
                snippet.casefold(),
                (text_body or "")[
                    :4000
                ].casefold(),
            ]
        )

        if (
            "instructure.com" in sender
            or "canvas" in sender
            or "canvas" in content
        ):
            return "canvas"

        academic_terms = {
            "assignment",
            "quiz",
            "tutorial",
            "lecture",
            "lecturer",
            "course",
            "module",
            "deadline",
            "submission",
            "exam",
            "class",
        }

        campus_terms = {
            "campus",
            "seminar",
            "workshop",
            "career fair",
            "student event",
            "registration",
            "nus",
            "university event",
        }

        academic_sender = any(
            domain in sender
            for domain in (
                "nus.edu.sg",
                "taylors.edu.my",
                ".edu.",
                ".ac.",
            )
        )

        if any(
            term in content
            for term in campus_terms
        ):
            return "campus"

        if (
            academic_sender
            or any(
                term in content
                for term in academic_terms
            )
        ):
            return "academic"

        return "unrelated"

    @staticmethod
    def _notification_sort_key(
        notification: GmailNotification,
    ) -> datetime:
        return (
            notification.sent_at
            or notification.internal_date
            or notification.created_at
        )

    @staticmethod
    def _truncate(
        value: str,
        limit: int,
    ) -> str:
        return str(value).strip()[:limit]

    @classmethod
    def _optional_truncate(
        cls,
        value: str | None,
        limit: int,
    ) -> str | None:
        if value is None:
            return None

        cleaned = cls._truncate(
            value,
            limit,
        )

        return cleaned or None

    @staticmethod
    def _deserialize(
        data: dict[str, Any],
    ) -> GmailNotification:
        required_strings = (
            "user_id",
            "message_id",
            "subject",
            "relevance",
        )

        for field in required_strings:
            if not isinstance(
                data.get(field),
                str,
            ):
                raise GmailNotificationError(
                    "Gmail notification is "
                    f"missing {field}"
                )

        relevance = data["relevance"]

        if relevance not in {
            "canvas",
            "academic",
            "campus",
            "unrelated",
        }:
            raise GmailNotificationError(
                "Gmail notification relevance "
                "is invalid"
            )

        created_at = data.get("created_at")
        updated_at = data.get("updated_at")

        if not isinstance(
            created_at,
            datetime,
        ) or not isinstance(
            updated_at,
            datetime,
        ):
            raise GmailNotificationError(
                "Gmail notification timestamps "
                "are invalid"
            )

        labels = data.get("labels", [])
        attachment_names = data.get(
            "attachment_names",
            [],
        )

        if not isinstance(
            labels,
            list,
        ) or not isinstance(
            attachment_names,
            list,
        ):
            raise GmailNotificationError(
                "Gmail notification lists are "
                "invalid"
            )

        return GmailNotification(
            user_id=data["user_id"],
            message_id=data["message_id"],
            thread_id=(
                data.get("thread_id")
                if isinstance(
                    data.get("thread_id"),
                    str,
                )
                else None
            ),
            history_id=(
                data.get("history_id")
                if isinstance(
                    data.get("history_id"),
                    str,
                )
                else None
            ),
            subject=data["subject"],
            from_address=(
                data.get("from_address")
                if isinstance(
                    data.get("from_address"),
                    str,
                )
                else None
            ),
            sent_at=(
                data.get("sent_at")
                if isinstance(
                    data.get("sent_at"),
                    datetime,
                )
                else None
            ),
            internal_date=(
                data.get("internal_date")
                if isinstance(
                    data.get("internal_date"),
                    datetime,
                )
                else None
            ),
            snippet=(
                data.get("snippet")
                if isinstance(
                    data.get("snippet"),
                    str,
                )
                else ""
            ),
            text_body=(
                data.get("text_body")
                if isinstance(
                    data.get("text_body"),
                    str,
                )
                else None
            ),
            labels=tuple(
                label
                for label in labels
                if isinstance(label, str)
            ),
            attachment_names=tuple(
                name
                for name in attachment_names
                if isinstance(name, str)
            ),
            relevance=relevance,
            is_relevant=(
                data.get("is_relevant")
                is True
            ),
            published=(
                data.get("published")
                is True
            ),
            notion_page_id=(
                data.get("notion_page_id")
                if isinstance(
                    data.get(
                        "notion_page_id"
                    ),
                    str,
                )
                else None
            ),
            notion_page_url=(
                data.get("notion_page_url")
                if isinstance(
                    data.get(
                        "notion_page_url"
                    ),
                    str,
                )
                else None
            ),
            created_at=created_at,
            updated_at=updated_at,
            published_at=(
                data.get("published_at")
                if isinstance(
                    data.get(
                        "published_at"
                    ),
                    datetime,
                )
                else None
            ),
        )