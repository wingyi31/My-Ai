import asyncio

import httpx

from app.connectors.notion import (
    NotionClient,
)
from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    api_key = (
        settings.notion_api_key
        .get_secret_value()
        if settings.notion_api_key
        is not None
        else None
    )

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(
            settings
            .notion_request_timeout_seconds
        ),
        follow_redirects=False,
        trust_env=settings.http_trust_env,
    ) as http_client:
        client = NotionClient(
            http_client=http_client,
            api_key=api_key,
            api_version=(
                settings.notion_api_version
            ),
            base_url=(
                settings.notion_base_url
            ),
            parent_page_id=(
                settings.notion_parent_page_id
            ),
        )

        connection = (
            await client.verify_connection()
        )
        parent_accessible = (
            await client.verify_parent_access()
        )

        print(
            {
                "status": "PASS",
                "configured": (
                    client.is_configured
                ),
                "write_configured": (
                    client.is_write_configured
                ),
                "parent_accessible": (
                    parent_accessible
                ),
                "user_id": connection.user_id,
                "name": connection.name,
                "type": connection.user_type,
            }
        )


if __name__ == "__main__":
    asyncio.run(main())