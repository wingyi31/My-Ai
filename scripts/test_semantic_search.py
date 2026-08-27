import asyncio
import os
import sys

from dotenv import load_dotenv

from app.repositories.firestore_client import (
    get_firestore_client,
)
from app.services.embedding_service import (
    VertexEmbeddingService,
)
from app.services.semantic_search_service import (
    SemanticSearchService,
)


async def main() -> None:
    if len(sys.argv) < 4:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_semantic_search "
            "<user_id> <course_id> "
            "<question>"
        )

    load_dotenv()

    user_id = sys.argv[1]
    course_id = sys.argv[2]

    question = " ".join(
        sys.argv[3:]
    )

    project_id = os.getenv(
        "GOOGLE_CLOUD_PROJECT"
    )

    if not project_id:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT "
            "is missing from .env"
        )

    location = os.getenv(
        "GOOGLE_CLOUD_LOCATION",
        "global",
    )

    model = os.getenv(
        "EMBEDDING_MODEL",
        "gemini-embedding-001",
    )

    dimensions = int(
        os.getenv(
            "EMBEDDING_DIMENSION",
            "768",
        )
    )

    db = get_firestore_client()

    async with VertexEmbeddingService(
        project_id=project_id,
        location=location,
        model=model,
        dimensions=dimensions,
    ) as embedding_service:
        search_service = (
            SemanticSearchService(
                db=db,
                embedding_service=(
                    embedding_service
                ),
            )
        )

        results = (
            await search_service
            .search_course(
                user_id=user_id,
                course_id=course_id,
                question=question,
                limit=8,
            )
        )

    print()
    print("Question:", question)
    print("Results found:", len(results))

    for position, result in enumerate(
        results,
        start=1,
    ):
        normalized_text = " ".join(
            result.text.split()
        )

        preview = normalized_text[:500]

        print()
        print(
            f"Result {position}"
        )
        print(
            "Similarity:",
            round(
                result.similarity,
                4,
            ),
        )
        print(
            "Cosine distance:",
            round(
                result.distance,
                4,
            ),
        )
        print(
            "File:",
            result.filename,
        )
        print(
            "Page:",
            result.page_number,
        )
        print(
            "Chunk:",
            result.chunk_id,
        )
        print(
            "Path:",
            result.document_path,
        )
        print(
            "Text:",
            preview,
        )


if __name__ == "__main__":
    asyncio.run(main())