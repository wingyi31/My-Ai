from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.connectors.gmail.client import GmailHistoryExpiredError
from app.connectors.gmail.service import GmailService


class GmailSyncStateError(RuntimeError):
    pass


class JsonGmailSyncStateStore:
    """Small local checkpoint store; replace with durable storage when scaling out."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load_history_id(self) -> str | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GmailSyncStateError(
                f"Could not read Gmail sync state from {self._path}"
            ) from exc
        history_id = payload.get("history_id") if isinstance(payload, dict) else None
        if not isinstance(history_id, str) or not history_id:
            raise GmailSyncStateError(
                f"Gmail sync state {self._path} has no history_id"
            )
        return history_id

    def save_history_id(self, history_id: str) -> None:
        if not history_id:
            raise GmailSyncStateError("Cannot save an empty Gmail history ID")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(
                {
                    "history_id": history_id,
                    "updated_at": datetime.now(UTC).isoformat(),
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
                prefix=f".{self._path.name}.",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                temporary_file.write(payload)
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._path)
        except OSError as exc:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
            raise GmailSyncStateError(
                f"Could not save Gmail sync state to {self._path}"
            ) from exc


class GmailSyncJob:
    def __init__(
        self,
        *,
        service: GmailService,
        state_store: JsonGmailSyncStateStore,
        query: str,
        max_messages: int,
    ) -> None:
        self._service = service
        self._state_store = state_store
        self._query = query
        self._max_messages = max_messages
        self._lock = asyncio.Lock()

    async def run(self) -> dict[str, Any]:
        """Run one sync and advance the history checkpoint only after success."""

        async with self._lock:
            start_history_id = self._state_store.load_history_id()
            recovered_from_expired_history = False
            try:
                result = await self._service.sync(
                    start_history_id=start_history_id,
                    query=self._query,
                    max_messages=self._max_messages,
                )
            except GmailHistoryExpiredError:
                result = await self._service.sync(
                    start_history_id=None,
                    query=self._query,
                    max_messages=self._max_messages,
                )
                recovered_from_expired_history = True

            self._state_store.save_history_id(result.history_id)
            payload = result.to_dict()
            payload["synced_at"] = datetime.now(UTC).isoformat()
            payload["recovered_from_expired_history"] = recovered_from_expired_history
            payload["note"] = (
                "Messages are parsed and exposed as metadata summaries. Inject an "
                "EmailProcessor handler to persist or index full parsed content."
            )
            return payload
