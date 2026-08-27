import asyncio
import math
import os

from dotenv import load_dotenv

from app.services.embedding_service import (
    VertexEmbeddingService,
)


def cosine_similarity(
    first: list[float],
    second: list[float],
) -> float:
    dot_product = sum(
        left * right
        for left, right in zip(first, second)
    )

    first_length = math.sqrt(
        sum(value * value for value in first)
    )

    second_length = math.sqrt(
        sum(value * value for value in second)
    )

    if first_length == 0 or second_length == 0:
        return 0.0

    return (
        dot_product
        / (first_length * second_length)
    )


async def main() -> None:
    load_dotenv()

    project_id = os.getenv(
        "GOOGLE_CLOUD_PROJECT"
    )

    if not project_id:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT is missing "
            "from .env"
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

    document_text = (
        "Cloud Storage stores uploaded PDF files "
        "as objects inside a private bucket."
    )

    query_text = (
        "Where are uploaded PDF files stored?"
    )

    async with VertexEmbeddingService(
        project_id=project_id,
        location=location,
        model=model,
        dimensions=dimensions,
    ) as embedding_service:
        document_vector = (
            await embedding_service.embed_document(
                document_text,
                title="PDF storage",
            )
        )

        query_vector = (
            await embedding_service.embed_query(
                query_text
            )
        )

    similarity = cosine_similarity(
        document_vector,
        query_vector,
    )

    print(
        "Document vector dimensions:",
        len(document_vector),
    )
    print(
        "Query vector dimensions:",
        len(query_vector),
    )
    print(
        "Cosine similarity:",
        round(similarity, 4),
    )
    print("Embedding generation successful")


if __name__ == "__main__":
    asyncio.run(main())