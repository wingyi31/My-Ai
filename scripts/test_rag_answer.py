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
from app.services.rag_answer_service import (
    RagAnswerService,
)
from app.services.semantic_search_service import (
    SemanticSearchService,
)


async def main() -> None:
    if len(sys.argv) < 4:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_rag_answer "
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

    embedding_model = os.getenv(
        "EMBEDDING_MODEL",
        "gemini-embedding-001",
    )

    embedding_dimensions = int(
        os.getenv(
            "EMBEDDING_DIMENSION",
            "768",
        )
    )

    generation_model = os.getenv(
        "GENERATION_MODEL",
        "gemini-3.7-flash",
    )

    db = get_firestore_client()

    async with VertexEmbeddingService(
        project_id=project_id,
        location=location,
        model=embedding_model,
        dimensions=embedding_dimensions,
    ) as embedding_service:
        search_service = (
            SemanticSearchService(
                db=db,
                embedding_service=(
                    embedding_service
                ),
            )
        )

        async with RagAnswerService(
            project_id=project_id,
            location=location,
            generation_model=(
                generation_model
            ),
            search_service=search_service,
        ) as rag_service:
            result = (
                await rag_service
                .answer_course_question(
                    user_id=user_id,
                    course_id=course_id,
                    question=question,
                    source_limit=8,
                )
            )

    print()
    print("Question:")
    print(result.question)

    print()
    print("Answer:")
    print(result.answer)

    print()
    print("Sources consulted:")

    for source_number, source in (
        enumerate(
            result.sources,
            start=1,
        )
    ):
        print(
            f"[Source {source_number}] "
            f"{source.filename}, "
            f"page {source.page_number}, "
            f"similarity="
            f"{source.similarity:.4f}"
        )


if __name__ == "__main__":
    asyncio.run(main())