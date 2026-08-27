import asyncio
import os
import sys

from dotenv import load_dotenv

from app.repositories.firestore_client import (
    get_firestore_client,
)
from app.repositories.firestore_repository import (
    CanvasFirestoreRepository,
)
from app.services.chunk_embedding_service import (
    embed_file_chunks,
)
from app.services.embedding_service import (
    VertexEmbeddingService,
)


async def main() -> None:
    if len(sys.argv) != 4:
        raise RuntimeError(
            "Usage: python -m "
            "scripts.test_chunk_embeddings "
            "<user_id> <course_id> <file_id>"
        )

    load_dotenv()

    user_id = sys.argv[1]
    course_id = sys.argv[2]
    canvas_file_id = sys.argv[3]

    project_id = os.getenv(
        "GOOGLE_CLOUD_PROJECT"
    )

    if not project_id:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT is missing"
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

    firestore_client = (
        get_firestore_client()
    )

    repository = CanvasFirestoreRepository(
        firestore_client
    )

    async with VertexEmbeddingService(
        project_id=project_id,
        location=location,
        model=model,
        dimensions=dimensions,
    ) as embedding_service:
        stats = await embed_file_chunks(
            user_id=user_id,
            course_id=course_id,
            canvas_file_id=canvas_file_id,
            repository=repository,
            embedding_service=(
                embedding_service
            ),
        )

    print()
    print(
        "Chunk embedding completed:",
        stats,
    )


if __name__ == "__main__":
    asyncio.run(main())