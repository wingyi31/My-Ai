"""Read-only Gmail connector."""

from app.connectors.gmail.client import GmailApiError, GmailClient
from app.connectors.gmail.oauth import GmailNotConfiguredError

__all__ = ["GmailApiError", "GmailClient", "GmailNotConfiguredError"]
