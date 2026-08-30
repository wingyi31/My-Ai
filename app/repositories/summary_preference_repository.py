from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from google.cloud import firestore


DetailLevel = Literal[
    "concise",
    "balanced",
    "detailed",
]

VALID_DETAIL_LEVELS = {
    "concise",
    "balanced",
    "detailed",
}

SECTION_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{1,49}$"
)

DEFAULT_SECTION_ORDER = (
    "overview",
    "learning_objectives",
    "core_concepts",
    "worked_examples",
    "important_formulas",
    "common_mistakes",
    "exam_focus",
    "practice_questions",
    "sources",
)


class SummaryPreferenceError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class SummaryPreferences:
    user_id: str
    detail_level: DetailLevel
    section_order: tuple[str, ...]
    preferred_language: str
    include_flashcards: bool
    include_source_links: bool
    version: int
    confirmed: bool
    updated_at: datetime | None


class SummaryPreferenceRepository:

    def __init__(
        self,
        db: firestore.AsyncClient,
    ) -> None:
        self._db = db

    @staticmethod
    def _clean_user_id(
        user_id: str,
    ) -> str:
        cleaned = str(user_id).strip()

        if not cleaned:
            raise ValueError(
                "User ID cannot be empty"
            )

        if "/" in cleaned:
            raise ValueError(
                "User ID cannot contain '/'"
            )

        return cleaned

    @staticmethod
    def _clean_sections(
        section_order: list[str]
        | tuple[str, ...],
    ) -> tuple[str, ...]:
        cleaned = tuple(
            str(section).strip()
            for section in section_order
        )

        if not 1 <= len(cleaned) <= 12:
            raise ValueError(
                "Summary structure must contain "
                "between 1 and 12 sections"
            )

        if len(set(cleaned)) != len(cleaned):
            raise ValueError(
                "Summary sections cannot be "
                "duplicated"
            )

        for section in cleaned:
            if not SECTION_PATTERN.fullmatch(
                section
            ):
                raise ValueError(
                    "Summary section names must "
                    "use lowercase snake_case"
                )

        return cleaned

    def _preference_ref(
        self,
        *,
        user_id: str,
    ):
        return (
            self._db
            .collection("users")
            .document(user_id)
            .collection("semantic_memory")
            .document("summary_preferences")
        )

    @staticmethod
    def default_preferences(
        *,
        user_id: str,
    ) -> SummaryPreferences:
        return SummaryPreferences(
            user_id=user_id,
            detail_level="balanced",
            section_order=(
                DEFAULT_SECTION_ORDER
            ),
            preferred_language="English",
            include_flashcards=True,
            include_source_links=True,
            version=0,
            confirmed=False,
            updated_at=None,
        )

    async def get_summary_preferences(
        self,
        *,
        user_id: str,
    ) -> SummaryPreferences:
        cleaned_user_id = (
            self._clean_user_id(user_id)
        )

        snapshot = await self._preference_ref(
            user_id=cleaned_user_id,
        ).get()

        if not snapshot.exists:
            return self.default_preferences(
                user_id=cleaned_user_id
            )

        data = snapshot.to_dict()

        if not isinstance(data, dict):
            raise SummaryPreferenceError(
                "Summary preferences contain "
                "invalid data"
            )

        detail_level = data.get(
            "detail_level"
        )
        section_order = data.get(
            "section_order"
        )
        preferred_language = data.get(
            "preferred_language"
        )
        include_flashcards = data.get(
            "include_flashcards"
        )
        include_source_links = data.get(
            "include_source_links"
        )
        version = data.get("version")
        confirmed = data.get("confirmed")
        updated_at = data.get("updated_at")

        if (
            detail_level
            not in VALID_DETAIL_LEVELS
            or not isinstance(
                section_order,
                list,
            )
            or not isinstance(
                preferred_language,
                str,
            )
            or not preferred_language.strip()
            or not isinstance(
                include_flashcards,
                bool,
            )
            or not isinstance(
                include_source_links,
                bool,
            )
            or not isinstance(version, int)
            or version < 1
            or confirmed is not True
            or not isinstance(
                updated_at,
                datetime,
            )
        ):
            raise SummaryPreferenceError(
                "Summary preferences contain "
                "invalid fields"
            )

        try:
            cleaned_sections = (
                self._clean_sections(
                    section_order
                )
            )
        except ValueError as error:
            raise SummaryPreferenceError(
                str(error)
            ) from error

        return SummaryPreferences(
            user_id=cleaned_user_id,
            detail_level=detail_level,
            section_order=cleaned_sections,
            preferred_language=(
                preferred_language.strip()
            ),
            include_flashcards=(
                include_flashcards
            ),
            include_source_links=(
                include_source_links
            ),
            version=version,
            confirmed=True,
            updated_at=updated_at,
        )

    async def save_summary_preferences(
        self,
        *,
        user_id: str,
        detail_level: DetailLevel,
        section_order: list[str]
        | tuple[str, ...],
        preferred_language: str,
        include_flashcards: bool,
        include_source_links: bool,
    ) -> SummaryPreferences:
        cleaned_user_id = (
            self._clean_user_id(user_id)
        )

        if (
            detail_level
            not in VALID_DETAIL_LEVELS
        ):
            raise ValueError(
                "Detail level must be concise, "
                "balanced, or detailed"
            )

        cleaned_sections = (
            self._clean_sections(
                section_order
            )
        )
        cleaned_language = str(
            preferred_language
        ).strip()

        if not cleaned_language:
            raise ValueError(
                "Preferred language cannot be "
                "empty"
            )

        if len(cleaned_language) > 50:
            raise ValueError(
                "Preferred language is too long"
            )

        if not isinstance(
            include_flashcards,
            bool,
        ):
            raise ValueError(
                "include_flashcards must be "
                "a boolean"
            )

        if not isinstance(
            include_source_links,
            bool,
        ):
            raise ValueError(
                "include_source_links must be "
                "a boolean"
            )

        preference_ref = (
            self._preference_ref(
                user_id=cleaned_user_id
            )
        )
        snapshot = await preference_ref.get()
        existing_data = (
            snapshot.to_dict()
            if snapshot.exists
            else {}
        ) or {}
        existing_version = (
            existing_data.get("version", 0)
        )

        if not isinstance(
            existing_version,
            int,
        ):
            existing_version = 0

        updated_at = datetime.now(UTC)
        preferences = SummaryPreferences(
            user_id=cleaned_user_id,
            detail_level=detail_level,
            section_order=cleaned_sections,
            preferred_language=(
                cleaned_language
            ),
            include_flashcards=(
                include_flashcards
            ),
            include_source_links=(
                include_source_links
            ),
            version=existing_version + 1,
            confirmed=True,
            updated_at=updated_at,
        )

        await preference_ref.set(
            {
                "user_id": (
                    preferences.user_id
                ),
                "detail_level": (
                    preferences.detail_level
                ),
                "section_order": list(
                    preferences.section_order
                ),
                "preferred_language": (
                    preferences
                    .preferred_language
                ),
                "include_flashcards": (
                    preferences
                    .include_flashcards
                ),
                "include_source_links": (
                    preferences
                    .include_source_links
                ),
                "version": preferences.version,
                "confirmed": True,
                "updated_at": updated_at,
            }
        )

        return preferences