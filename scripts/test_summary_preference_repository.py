import asyncio
import uuid

from app.repositories.firestore_client import (
    get_firestore_client,
)
from app.repositories.summary_preference_repository import (
    SummaryPreferenceRepository,
)


async def main() -> None:
    db = get_firestore_client()
    repository = SummaryPreferenceRepository(
        db
    )
    user_id = (
        "summary-preference-test-"
        f"{uuid.uuid4().hex}"
    )

    preference_ref = (
        db.collection("users")
        .document(user_id)
        .collection("semantic_memory")
        .document("summary_preferences")
    )

    try:
        defaults = await (
            repository.get_summary_preferences(
                user_id=user_id
            )
        )

        assert defaults.version == 0
        assert defaults.confirmed is False
        assert defaults.detail_level == (
            "balanced"
        )

        saved = await (
            repository.save_summary_preferences(
                user_id=user_id,
                detail_level="detailed",
                section_order=[
                    "overview",
                    "core_concepts",
                    "worked_examples",
                    "exam_focus",
                    "practice_questions",
                    "sources",
                ],
                preferred_language="English",
                include_flashcards=True,
                include_source_links=True,
            )
        )

        assert saved.version == 1
        assert saved.confirmed is True

        loaded = await (
            repository.get_summary_preferences(
                user_id=user_id
            )
        )

        assert loaded == saved

        try:
            await (
                repository
                .save_summary_preferences(
                    user_id=user_id,
                    detail_level="detailed",
                    section_order=[
                        "overview",
                        "overview",
                    ],
                    preferred_language=(
                        "English"
                    ),
                    include_flashcards=True,
                    include_source_links=True,
                )
            )
        except ValueError:
            duplicate_sections_blocked = True
        else:
            duplicate_sections_blocked = False

        assert duplicate_sections_blocked

        print(
            {
                "status": "PASS",
                "version": loaded.version,
                "detail_level": (
                    loaded.detail_level
                ),
                "sections": list(
                    loaded.section_order
                ),
                "duplicate_sections_blocked": (
                    duplicate_sections_blocked
                ),
            }
        )
    finally:
        await preference_ref.delete()
        db.close()
        print("Test record cleaned up.")


if __name__ == "__main__":
    asyncio.run(main())