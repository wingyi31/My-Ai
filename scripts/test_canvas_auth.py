import asyncio

from app.connectors.canvas.client import (
    CanvasReadOnlyClient,
)
from app.connectors.canvas.settings import (
    CanvasSettings,
)


async def main() -> None:
    settings = CanvasSettings()

    print("Canvas URL:", settings.base_url)
    print("Token configured:", bool(
        settings.access_token.get_secret_value()
    ))

    async with CanvasReadOnlyClient(
        base_url=settings.base_url,
        access_token=(
            settings.access_token.get_secret_value()
        ),
    ) as canvas:
        user = await canvas.get_json("users/self")

    print("Authentication successful")
    print("Canvas user ID:", user.get("id"))
    print("Canvas user name:", user.get("name"))


if __name__ == "__main__":
    asyncio.run(main())