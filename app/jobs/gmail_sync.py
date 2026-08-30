from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.connectors.gmail.client import (
    GmailHistoryExpiredError,
)
from app.connectors.gmail.service import (
    GmailService,
)
from app.repositories.gmail_notification_repository import (
    GmailNotificationRepository,
)


class GmailSyncStateError(RuntimeError):
    pass


class GmailSyncStateStore(Protocol):

    async def load_history_id(
        self,
    ) -> str | None:
        ...

    async def save_history_id(
        self,
        history_id: str,
        *,
        account_email: str | None = None,
    ) -> None:
        ...


class JsonGmailSyncStateStore:
    """Local development checkpoint store."""

    def __init__(
        self,
        path: Path,
    ) -> None:
        self._path = path

    async def load_history_id(
        self,
    ) -> str | None:
        if not self._path.exists():
            return None

        try:
            payload = json.loads(
                self._path.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, ValueError) as error:
            raise GmailSyncStateError(
                "Could not read Gmail sync "
                f"state from {self._path}"
            ) from error

        history_id = (
            payload.get("history_id")
            if isinstance(payload, dict)
            else None
        )

        if (
            not isinstance(history_id, str)
            or not history_id
        ):
            raise GmailSyncStateError(
                "Gmail sync state has no "
                "history ID"
            )

        return history_id

    async def save_history_id(
        self,
        history_id: str,
        *,
        account_email: str | None = None,
    ) -> None:
        if not history_id:
            raise GmailSyncStateError(
                "Cannot save an empty Gmail "
                "history ID"
            )

        self._path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = (
            json.dumps(
                {
                    "history_id": history_id,
                    "account_email": (
                        account_email
                    ),
                    "updated_at": (
                        datetime.now(UTC)
                        .isoformat()
                    ),
                },
                indent=2,
            )
            + "\n"
        )

        temporary_path: str | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=(
                    f".{self._path.name}."
                ),
                delete=False,
            ) as temporary_file:
                temporary_path = (
                    temporary_file.name
                )
                temporary_file.write(payload)

            os.chmod(temporary_path, 0o600)
            os.replace(
                temporary_path,
                self._path,
            )
        except OSError as error:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

            raise GmailSyncStateError(
                "Could not save Gmail sync "
                f"state to {self._path}"
            ) from error


class FirestoreGmailSyncStateStore:

    def __init__(
        self,
        *,
        repository: (
            GmailNotificationRepository
        ),
        user_id: str,
    ) -> None:
        cleaned_user_id = str(
            user_id
        ).strip()

        if not cleaned_user_id:
            raise ValueError(
                "Gmail sync user ID cannot "
                "be empty"
            )

        self._repository = repository
        self._user_id = cleaned_user_id

    async def load_history_id(
        self,
    ) -> str | None:
        return await (
            self._repository.load_history_id(
                user_id=self._user_id
            )
        )

    async def save_history_id(
        self,
        history_id: str,
        *,
        account_email: str | None = None,
    ) -> None:
        await self._repository.save_history_id(
            user_id=self._user_id,
            history_id=history_id,
            account_email=account_email,
        )


class GmailSyncJob:

    def __init__(
        self,
        *,
        service: GmailService,
        state_store: GmailSyncStateStore,
        query: str,
        max_messages: int,
    ) -> None:
        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError(
                "Gmail sync query cannot be "
                "empty"
            )

        self._service = service
        self._state_store = state_store
        self._query = cleaned_query
        self._max_messages = max_messages
        self._lock = asyncio.Lock()

    async def run(
        self,
    ) -> dict[str, Any]:
        async with self._lock:
            start_history_id = await (
                self._state_store
                .load_history_id()
            )
            recovered = False

            try:
                result = await (
                    self._service.sync(
                        start_history_id=(
                            start_history_id
                        ),
                        query=self._query,
                        max_messages=(
                            self._max_messages
                        ),
                    )
                )
            except GmailHistoryExpiredError:
                result = await (
                    self._service.sync(
                        start_history_id=None,
                        query=self._query,
                        max_messages=(
                            self._max_messages
                        ),
                    )
                )
                recovered = True

            # EmailProcessor handlers have
            # completed successfully before the
            # checkpoint is advanced.
            await (
                self._state_store
                .save_history_id(
                    result.history_id,
                    account_email=(
                        result.account_email
                    ),
                )
            )

            payload = result.to_dict()
            payload["synced_at"] = (
                datetime.now(UTC).isoformat()
            )
            payload[
                "recovered_from_expired_history"
            ] = recovered
            payload["note"] = (
                "Relevant academic messages "
                "were persisted before the "
                "Firestore history checkpoint "
                "was advanced."
            )

            return payload