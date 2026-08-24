import base64
from datetime import UTC, datetime

import pytest

from app.connectors.gmail.parser import GmailMessageParseError, parse_gmail_message


def encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def test_parse_multipart_message_and_attachment() -> None:
    message = {
        "id": "message-1",
        "threadId": "thread-1",
        "historyId": "123",
        "internalDate": "1724515200000",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "Hello",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "Subject", "value": "=?utf-8?q?Hello_=E2=9C=93?="},
                {"name": "From", "value": "Sender <sender@example.com>"},
                {
                    "name": "To",
                    "value": "One <one@example.com>, two@example.com",
                },
                {"name": "Date", "value": "Sat, 24 Aug 2024 16:00:00 +0800"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "filename": "",
                    "headers": [
                        {
                            "name": "Content-Type",
                            "value": "text/plain; charset=iso-8859-1",
                        }
                    ],
                    "body": {"data": encoded("caf\u00e9".encode("iso-8859-1"))},
                },
                {
                    "mimeType": "text/html",
                    "filename": "",
                    "body": {"data": encoded(b"<p>caf&eacute;</p>")},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "report.pdf",
                    "body": {"attachmentId": "attachment-1", "size": 42},
                },
            ],
        },
    }

    parsed = parse_gmail_message(message)

    assert parsed.message_id == "message-1"
    assert parsed.subject == "Hello \u2713"
    assert parsed.from_address == "sender@example.com"
    assert parsed.to_addresses == ("one@example.com", "two@example.com")
    assert parsed.sent_at == datetime(2024, 8, 24, 8, 0, tzinfo=UTC)
    assert parsed.text_body == "caf\u00e9"
    assert parsed.html_body == "<p>caf&eacute;</p>"
    assert parsed.attachments[0].attachment_id == "attachment-1"
    assert parsed.to_summary()["attachment_count"] == 1


def test_parse_rejects_payload_without_message_id() -> None:
    with pytest.raises(GmailMessageParseError, match="no id"):
        parse_gmail_message({"payload": {}})
