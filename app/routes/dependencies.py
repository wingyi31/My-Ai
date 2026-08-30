import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def verify_scheduler_secret(
    x_scheduler_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Optionally protect scheduler routes with the configured shared secret."""
    configured = get_settings().scheduler_shared_secret
    if configured is None:
        return

    expected = configured.get_secret_value()
    if x_scheduler_secret is None or not secrets.compare_digest(
        x_scheduler_secret, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid scheduler secret",
        )
