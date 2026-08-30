from dataclasses import dataclass
import hashlib

from app.services.pdf_extraction_service import (
    PdfExtractionResult,
)


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_id: str
    page_number: int
    chunk_index: int
    text: str
    start_character: int
    end_character: int
    text_hash: str


class TextChunkingService:
    def __init__(
        self,
        *,
        maximum_characters: int = 1200,
        overlap_characters: int = 200,
    ):
        if overlap_characters >= maximum_characters:
            raise ValueError(
                "Chunk overlap must be smaller "
                "than the maximum chunk size"
            )

        self.maximum_characters = (
            maximum_characters
        )
        self.overlap_characters = (
            overlap_characters
        )

    def chunk(
        self,
        extraction: PdfExtractionResult,
    ) -> list[TextChunk]:
        chunks: list[TextChunk] = []

        for page in extraction.pages:
            page_text = page.text.strip()

            if not page_text:
                continue

            start = 0
            chunk_index = 0

            while start < len(page_text):
                target_end = min(
                    start
                    + self.maximum_characters,
                    len(page_text),
                )

                end = self._find_boundary(
                    text=page_text,
                    start=start,
                    target_end=target_end,
                )

                chunk_text = (
                    page_text[start:end].strip()
                )

                if chunk_text:
                    chunk_id = (
                        f"p{page.page_number:04d}-"
                        f"c{chunk_index:04d}"
                    )

                    text_hash = hashlib.sha256(
                        chunk_text.encode("utf-8")
                    ).hexdigest()

                    chunks.append(
                        TextChunk(
                            chunk_id=chunk_id,
                            page_number=(
                                page.page_number
                            ),
                            chunk_index=chunk_index,
                            text=chunk_text,
                            start_character=start,
                            end_character=end,
                            text_hash=text_hash,
                        )
                    )

                    chunk_index += 1

                if end >= len(page_text):
                    break

                next_start = max(
                    0,
                    end
                    - self.overlap_characters,
                )

                if next_start <= start:
                    next_start = end

                start = next_start

        return chunks

    def _find_boundary(
        self,
        *,
        text: str,
        start: int,
        target_end: int,
    ) -> int:
        if target_end >= len(text):
            return len(text)

        window = text[start:target_end]

        minimum_boundary = int(
            len(window) * 0.6
        )

        possible_boundaries = [
            window.rfind(
                "\n",
                minimum_boundary,
            ),
            window.rfind(
                ". ",
                minimum_boundary,
            ),
            window.rfind(
                "? ",
                minimum_boundary,
            ),
            window.rfind(
                "! ",
                minimum_boundary,
            ),
            window.rfind(
                " ",
                minimum_boundary,
            ),
        ]

        boundary = max(possible_boundaries)

        if boundary <= 0:
            return target_end

        return start + boundary + 1