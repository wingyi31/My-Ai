from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from app.connectors.gmail.parser import ParsedEmail, parse_gmail_message

EmailHandler = Callable[[ParsedEmail], Awaitable[None] | None]


class EmailProcessor:
    """Parse a Gmail payload, then optionally hand it to application persistence.

    The handler is deliberately injected: this connector does not assume a database
    schema. A repository/indexing function can be supplied without changing sync or
    Gmail API code.
    """

    def __init__(self, handler: EmailHandler | None = None) -> None:
        self._handler = handler

    async def process(self, raw_message: dict) -> ParsedEmail:
        email = parse_gmail_message(raw_message)
        if self._handler is not None:
            result = self._handler(email)
            if inspect.isawaitable(result):
                await result
        return email
