import asyncio
import json
from pathlib import Path

from app.connectors.gmail.client import HistoryListPage, MessageListPage
from app.connectors.gmail.service import GmailService
from app.jobs.gmail_sync import GmailSyncJob, JsonGmailSyncStateStore
from app.workers.email_processor import EmailProcessor


def raw_message(message_id: str) -> dict:
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "historyId": "100",
        "internalDate": "1724515200000",
        "labelIds": ["INBOX"],
        "snippet": "preview",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": f"Subject {message_id}"},
                {"name": "From", "value": "sender@example.com"},
            ],
            "body": {"data": "SGVsbG8"},
        },
    }


class FakeGmailClient:
    def __init__(self) -> None:
        self.requested_message_ids: list[str] = []

    async def get_profile(self) -> dict:
        return {"emailAddress": "student@example.com", "historyId": "100"}

    async def list_messages(self, **kwargs) -> MessageListPage:
        assert kwargs["query"] == "in:inbox"
        return MessageListPage(("one", "two"), None, 2)

    async def list_history(self, **kwargs) -> HistoryListPage:
        assert kwargs["start_history_id"] == "100"
        return HistoryListPage(
            history=(
                {
                    "id": "101",
                    "messagesAdded": [{"message": {"id": "three"}}],
                },
            ),
            next_page_token=None,
            latest_history_id="102",
        )

    async def get_message(self, message_id: str) -> dict:
        self.requested_message_ids.append(message_id)
        return raw_message(message_id)


def test_bootstrap_processes_messages_and_job_saves_checkpoint(tmp_path: Path) -> None:
    async def run() -> None:
        client = FakeGmailClient()
        service = GmailService(client, EmailProcessor())  # type: ignore[arg-type]
        state_path = tmp_path / "state.json"
        job = GmailSyncJob(
            service=service,
            state_store=JsonGmailSyncStateStore(state_path),
            query="in:inbox",
            max_messages=50,
        )

        result = await job.run()

        assert result["mode"] == "bootstrap"
        assert result["processed_count"] == 2
        assert result["messages"][0]["subject"] == "Subject one"
        assert json.loads(state_path.read_text())["history_id"] == "100"

    asyncio.run(run())


def test_incremental_sync_uses_saved_history(tmp_path: Path) -> None:
    async def run() -> None:
        state_store = JsonGmailSyncStateStore(tmp_path / "state.json")
        state_store.save_history_id("100")
        client = FakeGmailClient()
        service = GmailService(client, EmailProcessor())  # type: ignore[arg-type]
        job = GmailSyncJob(
            service=service,
            state_store=state_store,
            query="in:inbox",
            max_messages=50,
        )

        result = await job.run()

        assert result["mode"] == "incremental"
        assert client.requested_message_ids == ["three"]
        assert json.loads((tmp_path / "state.json").read_text())["history_id"] == "102"

    asyncio.run(run())
