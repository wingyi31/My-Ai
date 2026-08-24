from __future__ import annotations

import base64
import binascii
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any


class GmailMessageParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GmailAttachment:
    filename: str
    mime_type: str
    size: int
    attachment_id: str | None


@dataclass(frozen=True, slots=True)
class ParsedEmail:
    message_id: str
    thread_id: str | None
    history_id: str | None
    internal_date: datetime | None
    sent_at: datetime | None
    subject: str
    from_address: str | None
    to_addresses: tuple[str, ...]
    cc_addresses: tuple[str, ...]
    snippet: str
    text_body: str | None
    html_body: str | None
    labels: tuple[str, ...]
    attachments: tuple[GmailAttachment, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["internal_date"] = (
            self.internal_date.isoformat() if self.internal_date else None
        )
        payload["sent_at"] = self.sent_at.isoformat() if self.sent_at else None
        return payload

    def to_summary(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "subject": self.subject,
            "from": self.from_address,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "labels": list(self.labels),
            "attachment_count": len(self.attachments),
        }


def parse_gmail_message(message: dict[str, Any]) -> ParsedEmail:
    """Convert a Gmail ``messages.get(format=full)`` payload to a stable model."""

    message_id = message.get("id")
    payload = message.get("payload")
    if not isinstance(message_id, str) or not message_id:
        raise GmailMessageParseError("Gmail message has no id")
    if not isinstance(payload, dict):
        raise GmailMessageParseError(f"Gmail message {message_id} has no MIME payload")

    headers = _headers_by_name(payload.get("headers"))
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[GmailAttachment] = []
    _walk_parts(payload, text_parts, html_parts, attachments)

    thread_id = message.get("threadId")
    history_id = message.get("historyId")
    labels = message.get("labelIds", [])
    snippet = message.get("snippet", "")
    return ParsedEmail(
        message_id=message_id,
        thread_id=thread_id if isinstance(thread_id, str) else None,
        history_id=history_id if isinstance(history_id, str) else None,
        internal_date=_parse_internal_date(message.get("internalDate")),
        sent_at=_parse_rfc_date(headers.get("date")),
        subject=_decode_header_value(headers.get("subject", "")),
        from_address=_single_address(headers.get("from")),
        to_addresses=_addresses(headers.get("to")),
        cc_addresses=_addresses(headers.get("cc")),
        snippet=snippet if isinstance(snippet, str) else "",
        text_body=_join_body_parts(text_parts),
        html_body=_join_body_parts(html_parts),
        labels=tuple(label for label in labels if isinstance(label, str)),
        attachments=tuple(attachments),
    )


def _headers_by_name(raw_headers: Any) -> dict[str, str]:
    if not isinstance(raw_headers, list):
        return {}
    headers: dict[str, str] = {}
    for item in raw_headers:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if isinstance(name, str) and isinstance(value, str):
            headers.setdefault(name.lower(), value)
    return headers


def _walk_parts(
    part: dict[str, Any],
    text_parts: list[str],
    html_parts: list[str],
    attachments: list[GmailAttachment],
) -> None:
    mime_type = part.get("mimeType", "application/octet-stream")
    filename = part.get("filename", "")
    body = part.get("body")
    body = body if isinstance(body, dict) else {}

    if isinstance(filename, str) and filename:
        size = body.get("size", 0)
        attachment_id = body.get("attachmentId")
        attachments.append(
            GmailAttachment(
                filename=_decode_header_value(filename),
                mime_type=mime_type
                if isinstance(mime_type, str)
                else "application/octet-stream",
                size=size if isinstance(size, int) else 0,
                attachment_id=(
                    attachment_id if isinstance(attachment_id, str) else None
                ),
            )
        )
    else:
        encoded_data = body.get("data")
        if isinstance(encoded_data, str) and isinstance(mime_type, str):
            content_type = _part_content_type(part) or mime_type
            decoded = _decode_body(encoded_data, content_type)
            if mime_type.lower().startswith("text/plain"):
                text_parts.append(decoded)
            elif mime_type.lower().startswith("text/html"):
                html_parts.append(decoded)

    child_parts = part.get("parts", [])
    if isinstance(child_parts, list):
        for child in child_parts:
            if isinstance(child, dict):
                _walk_parts(child, text_parts, html_parts, attachments)


def _decode_body(encoded_data: str, mime_type: str) -> str:
    padding = "=" * (-len(encoded_data) % 4)
    try:
        body = base64.urlsafe_b64decode(encoded_data + padding)
    except (ValueError, binascii.Error) as exc:
        raise GmailMessageParseError(
            "Gmail MIME body contained invalid base64"
        ) from exc

    charset = "utf-8"
    content_type = Message()
    content_type["content-type"] = mime_type
    detected_charset = content_type.get_content_charset()
    if detected_charset:
        charset = detected_charset
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _part_content_type(part: dict[str, Any]) -> str | None:
    headers = _headers_by_name(part.get("headers"))
    return headers.get("content-type")


def _decode_header_value(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeError):
        return value


def _addresses(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    parsed: list[str] = []
    for display_name, address in getaddresses([_decode_header_value(value)]):
        if address:
            parsed.append(address)
        elif display_name:
            parsed.append(display_name)
    return tuple(parsed)


def _single_address(value: str | None) -> str | None:
    addresses = _addresses(value)
    return addresses[0] if addresses else None


def _parse_rfc_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_internal_date(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _join_body_parts(parts: list[str]) -> str | None:
    cleaned = [part.strip() for part in parts if part.strip()]
    return "\n\n".join(cleaned) if cleaned else None
