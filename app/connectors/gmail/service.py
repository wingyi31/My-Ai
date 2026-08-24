from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from app.connectors.gmail.client import GmailApiError, GmailClient
from app.connectors.gmail.parser import ParsedEmail
from app.workers.email_processor import EmailProcessor

SyncMode = Literal["bootstrap", "incremental"]


class GmailMessageProcessingError(RuntimeError):
    def __init__(self, failed_message_ids: tuple[str, ...]) -> None:
        self.failed_message_ids = failed_message_ids
        joined = ", ".join(failed_message_ids[:5])
        suffix = "..." if len(failed_message_ids) > 5 else ""
        super().__init__(f"Failed to process Gmail messages: {joined}{suffix}")


@dataclass(frozen=True, slots=True)
class GmailSyncResult:
    mode: SyncMode
    account_email: str
    history_id: str
    messages: tuple[ParsedEmail, ...]
    skipped_message_ids: tuple[str, ...]
    available_message_estimate: int | None
    more_history_available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "success",
            "source": "gmail",
            "mode": self.mode,
            "account_email": self.account_email,
            "history_id": self.history_id,
            "processed_count": len(self.messages),
            "skipped_count": len(self.skipped_message_ids),
            "skipped_message_ids": list(self.skipped_message_ids),
            "available_message_estimate": self.available_message_estimate,
            "more_history_available": self.more_history_available,
            "messages": [email.to_summary() for email in self.messages[:20]],
        }


class GmailService:
    """Fetch and process either a bounded bootstrap or incremental Gmail history."""

    def __init__(
        self,
        client: GmailClient,
        processor: EmailProcessor,
        *,
        fetch_concurrency: int = 5,
    ) -> None:
        self._client = client
        self._processor = processor
        self._fetch_concurrency = max(fetch_concurrency, 1)

    async def sync(
        self,
        *,
        start_history_id: str | None,
        query: str,
        max_messages: int,
    ) -> GmailSyncResult:
        profile = await self._client.get_profile()
        account_email = profile["emailAddress"]

        if start_history_id is None:
            message_ids, estimate = await self._bootstrap_message_ids(
                query=query,
                max_messages=max_messages,
            )
            # This snapshot is deliberately taken before list_messages. Messages that
            # arrive during bootstrap are therefore visible to the next history sync.
            history_id = profile["historyId"]
            mode: SyncMode = "bootstrap"
            more_history_available = bool(
                estimate is not None and estimate > len(message_ids)
            )
        else:
            (
                message_ids,
                history_id,
                more_history_available,
            ) = await self._incremental_message_ids(
                start_history_id=start_history_id,
                max_messages=max_messages,
            )
            estimate = None
            mode = "incremental"

        messages, skipped = await self._fetch_and_process(message_ids)
        return GmailSyncResult(
            mode=mode,
            account_email=account_email,
            history_id=history_id,
            messages=messages,
            skipped_message_ids=skipped,
            available_message_estimate=estimate,
            more_history_available=more_history_available,
        )

    async def _bootstrap_message_ids(
        self,
        *,
        query: str,
        max_messages: int,
    ) -> tuple[tuple[str, ...], int | None]:
        message_ids: list[str] = []
        page_token: str | None = None
        estimate: int | None = None
        while len(message_ids) < max_messages:
            page = await self._client.list_messages(
                query=query,
                max_results=max_messages - len(message_ids),
                page_token=page_token,
            )
            if estimate is None:
                estimate = page.result_size_estimate
            message_ids.extend(page.message_ids)
            page_token = page.next_page_token
            if not page_token:
                break
        return tuple(message_ids[:max_messages]), estimate

    async def _incremental_message_ids(
        self,
        *,
        start_history_id: str,
        max_messages: int,
    ) -> tuple[tuple[str, ...], str, bool]:
        message_ids: list[str] = []
        seen_ids: set[str] = set()
        checkpoint = start_history_id
        page_token: str | None = None

        while True:
            page = await self._client.list_history(
                start_history_id=start_history_id,
                page_token=page_token,
            )
            for record in page.history:
                record_message_ids = self._message_ids_from_history_record(record)
                new_ids = [item for item in record_message_ids if item not in seen_ids]

                # Never split one history record: its ID is the safe checkpoint unit.
                if (
                    new_ids
                    and message_ids
                    and len(message_ids) + len(new_ids) > max_messages
                ):
                    return tuple(message_ids), checkpoint, True

                message_ids.extend(new_ids)
                seen_ids.update(new_ids)
                record_id = record.get("id")
                if isinstance(record_id, str):
                    checkpoint = record_id

                if len(message_ids) >= max_messages:
                    return tuple(message_ids), checkpoint, True

            page_token = page.next_page_token
            if not page_token:
                return tuple(message_ids), page.latest_history_id, False

    @staticmethod
    def _message_ids_from_history_record(record: dict[str, Any]) -> list[str]:
        raw_added = record.get("messagesAdded", [])
        if not isinstance(raw_added, list):
            return []
        message_ids: list[str] = []
        for addition in raw_added:
            if not isinstance(addition, dict):
                continue
            message = addition.get("message")
            if isinstance(message, dict) and isinstance(message.get("id"), str):
                message_ids.append(message["id"])
        return message_ids

    async def _fetch_and_process(
        self,
        message_ids: tuple[str, ...],
    ) -> tuple[tuple[ParsedEmail, ...], tuple[str, ...]]:
        semaphore = asyncio.Semaphore(self._fetch_concurrency)

        async def process_one(message_id: str) -> ParsedEmail | None:
            async with semaphore:
                try:
                    raw_message = await self._client.get_message(message_id)
                except GmailApiError as exc:
                    # A message can be removed between history/list and messages.get.
                    if exc.status_code == 404:
                        return None
                    raise
                return await self._processor.process(raw_message)

        results = await asyncio.gather(
            *(process_one(message_id) for message_id in message_ids),
            return_exceptions=True,
        )
        failed = tuple(
            message_id
            for message_id, result in zip(message_ids, results, strict=True)
            if isinstance(result, BaseException)
        )
        if failed:
            raise GmailMessageProcessingError(failed)

        processed: list[ParsedEmail] = []
        skipped: list[str] = []
        for message_id, result in zip(message_ids, results, strict=True):
            if result is None:
                skipped.append(message_id)
            else:
                assert isinstance(result, ParsedEmail)
                processed.append(result)
        return tuple(processed), tuple(skipped)
