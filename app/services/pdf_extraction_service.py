from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader


@dataclass(frozen=True, slots=True)
class ExtractedPdfPage:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class PdfExtractionResult:
    pages: tuple[ExtractedPdfPage, ...]
    page_count: int
    total_characters: int
    needs_ocr: bool


class PdfExtractionService:

    def extract(
        self,
        pdf_content: bytes,
    ) -> PdfExtractionResult:
        if b"%PDF-" not in pdf_content[:1024]:
            raise ValueError(
                "Content is not a valid PDF"
            )

        reader = PdfReader(
            BytesIO(pdf_content),
            strict=False,
        )

        if reader.is_encrypted:
            result = reader.decrypt("")

            if result == 0:
                raise RuntimeError(
                    "PDF is password protected"
                )

        extracted_pages: list[
            ExtractedPdfPage
        ] = []

        alphanumeric_characters = 0

        for index, page in enumerate(
            reader.pages,
            start=1,
        ):
            raw_text = (
                page.extract_text() or ""
            )

            # Remove excessive whitespace while
            # retaining page line boundaries.
            cleaned_lines = [
                " ".join(line.split())
                for line in raw_text.splitlines()
                if line.strip()
            ]

            text = "\n".join(cleaned_lines)

            alphanumeric_characters += sum(
                character.isalnum()
                for character in text
            )

            extracted_pages.append(
                ExtractedPdfPage(
                    page_number=index,
                    text=text,
                )
            )

        total_characters = sum(
            len(page.text)
            for page in extracted_pages
        )

        minimum_expected_characters = max(
            50,
            len(extracted_pages) * 20,
        )

        needs_ocr = (
            alphanumeric_characters
            < minimum_expected_characters
        )

        return PdfExtractionResult(
            pages=tuple(extracted_pages),
            page_count=len(extracted_pages),
            total_characters=(
                total_characters
            ),
            needs_ocr=needs_ocr,
        )