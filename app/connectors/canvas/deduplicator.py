import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from app.models.source_item import (
    NormalizedSourceItem,
)


class ChangeType(str, Enum):
    NEW = "new"
    UNCHANGED = "unchanged"
    UPDATED = "updated"


@dataclass(frozen=True)
class DeduplicationResult:
    change_type: ChangeType
    revision_hash: str


def calculate_revision_hash(
    item: NormalizedSourceItem,
) -> str:
    payload = item.model_dump(
        mode="json",
        exclude={
            # Identity is checked separately.
            "source_key",

            # This is downstream classification,
            # not original Canvas content.
            "academic_category",
        },
    )

    # File ordering should not cause a false update.
    payload["file_references"] = sorted(
        payload["file_references"],
        key=lambda file: (
            file.get("canvas_file_id") or "",
            file.get("url") or "",
            file.get("link_text") or "",
        ),
    )

    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


def decide_change(
    item: NormalizedSourceItem,
    existing_revision_hash: str | None,
) -> DeduplicationResult:
    current_hash = calculate_revision_hash(item)

    if existing_revision_hash is None:
        change_type = ChangeType.NEW
    elif existing_revision_hash == current_hash:
        change_type = ChangeType.UNCHANGED
    else:
        change_type = ChangeType.UPDATED

    return DeduplicationResult(
        change_type=change_type,
        revision_hash=current_hash,
    )