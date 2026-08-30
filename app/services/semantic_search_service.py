from __future__ import annotations

from dataclasses import dataclass

from google.cloud.firestore_v1.base_query import (
    FieldFilter,
)
from google.cloud.firestore_v1.base_vector_query import (
    DistanceMeasure,
)
from google.cloud.firestore_v1.vector import (
    Vector,
)

from app.services.embedding_service import (
    VertexEmbeddingService,
)


@dataclass(frozen=True)
class SemanticSearchResult:
    chunk_id: str
    document_path: str
    canvas_file_id: str
    filename: str
    page_number: int | None
    chunk_index: int | None
    text: str
    distance: float

    @property
    def similarity(self) -> float:
        return 1.0 - self.distance


class SemanticSearchService:

    def __init__(
        self,
        *,
        db,
        embedding_service: (
            VertexEmbeddingService
        ),
    ) -> None:
        self.db = db
        self.embedding_service = (
            embedding_service
        )

    async def search_course(
        self,
        *,
        user_id: str,
        course_id: str,
        question: str,
        limit: int = 5,
    ) -> list[SemanticSearchResult]:
        cleaned_question = (
            question.strip()
        )

        if not cleaned_question:
            raise ValueError(
                "Search question cannot "
                "be empty"
            )

        if not 1 <= limit <= 100:
            raise ValueError(
                "Search limit must be "
                "between 1 and 100"
            )

        query_embedding = (
            await self.embedding_service
            .embed_query(cleaned_question)
        )

        chunks_query = (
            self.db
            .collection_group("chunks")
            .where(
                filter=FieldFilter(
                    "canvas_user_id",
                    "==",
                    str(user_id),
                )
            )
            .where(
                filter=FieldFilter(
                    "canvas_course_id",
                    "==",
                    str(course_id),
                )
            )
        )

        vector_query = (
            chunks_query.find_nearest(
                vector_field="embedding",
                query_vector=Vector(
                    query_embedding
                ),
                limit=limit,
                distance_measure=(
                    DistanceMeasure.COSINE
                ),
                distance_result_field=(
                    "vector_distance"
                ),
            )
        )

        results: list[
            SemanticSearchResult
        ] = []

        async for snapshot in (
            vector_query.stream()
        ):
            data = snapshot.to_dict() or {}

            distance_value = data.get(
                "vector_distance"
            )

            if distance_value is None:
                continue

            results.append(
                SemanticSearchResult(
                    chunk_id=snapshot.id,
                    document_path=(
                        snapshot.reference.path
                    ),
                    canvas_file_id=str(
                        data.get(
                            "canvas_file_id",
                            "",
                        )
                    ),
                    filename=str(
                        data.get(
                            "filename",
                            "",
                        )
                    ),
                    page_number=data.get(
                        "page_number"
                    ),
                    chunk_index=data.get(
                        "chunk_index"
                    ),
                    text=str(
                        data.get("text", "")
                    ),
                    distance=float(
                        distance_value
                    ),
                )
            )

        return results