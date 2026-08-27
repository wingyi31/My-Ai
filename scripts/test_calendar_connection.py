from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.connectors.calendar import (
    GoogleCalendarClient,
)
from app.connectors.gmail.oauth import (
    GmailCredentialStore,
    GmailOAuthClient,
    OAuthStateSigner,
)
from app.core.config import get_settings


def secret_value(
    value: Any,
) -> str | None:
    if value is None:
        return None

    return value.get_secret_value()


async def main() -> None:
    settings = get_settings()

    credential_store = GmailCredentialStore(
        configured_refresh_token=(
            secret_value(
                settings.gmail_refresh_token
            )
        ),
        path=settings.gmail_token_path,
    )

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(
            settings
            .gmail_request_timeout_seconds
        ),
        follow_redirects=False,
        trust_env=settings.http_trust_env,
    ) as http_client:
        oauth_client = GmailOAuthClient(
            http_client=http_client,
            client_id=secret_value(
                settings.gmail_client_id
            ),
            client_secret=secret_value(
                settings.gmail_client_secret
            ),
            redirect_uri=(
                settings.gmail_redirect_uri
            ),
            state_signer=OAuthStateSigner(
                secret_value(
                    settings
                    .gmail_oauth_state_secret
                )
            ),
        )

        calendar_client = (
            GoogleCalendarClient(
                http_client=http_client,
                oauth_client=oauth_client,
                credential_store=(
                    credential_store
                ),
            )
        )

        result = await (
            calendar_client
            .list_upcoming_events(
                max_results=1
            )
        )

        print(
            "Calendar timezone:",
            result["time_zone"],
        )
        print(
            "Calendar access role:",
            result["access_role"],
        )
        print(
            "Upcoming events returned:",
            len(result["events"]),
        )
        print(
            "Reusable Calendar client: OK"
        )


if __name__ == "__main__":
    asyncio.run(main())