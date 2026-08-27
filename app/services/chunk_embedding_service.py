from __future__ import annotations

import hashlib
from typing import Any

from app.repositories.firestore_repository import (
    CanvasFirestoreRepository,
)
from app.services.embedding_service import (
    VertexEmbeddingService,
)


def calculate_text_hash(
    text: str,
) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


async def embed_file_chunks(
    *,
    user_id: str,
    course_id: str,
    canvas_file_id: str,
    repository: CanvasFirestoreRepository,
    embedding_service: VertexEmbeddingService,
    batch_size: int = 20,
) -> dict[str, int]:
    chunks = await repository.list_file_chunks(
        user_id=user_id,
        course_id=course_id,
        canvas_file_id=canvas_file_id,
    )

    pending_chunks: list[
        dict[str, Any]
    ] = []

    skipped = 0
    empty = 0

    for chunk in chunks:
        text = str(
            chunk.get("text") or ""
        ).strip()

        if not text:
            empty += 1
            continue

        text_hash = str(
            chunk.get("text_hash") or ""
        )

        if not text_hash:
            text_hash = (
                calculate_text_hash(text)
            )

        chunk["text"] = text
        chunk["text_hash"] = text_hash

        already_current = (
            chunk.get("embedding")
            is not None
            and chunk.get(
                "embedding_text_hash"
            ) == text_hash
            and chunk.get(
                "embedding_model"
            ) == embedding_service.model
            and chunk.get(
                "embedding_dimensions"
            ) == embedding_service.dimensions
        )

        if already_current:
            skipped += 1
            continue

        pending_chunks.append(chunk)

    embedded = 0

    for start in range(
        0,
        len(pending_chunks),
        batch_size,
    ):
        chunk_batch = pending_chunks[
            start:start + batch_size
        ]

        texts = [
            str(chunk["text"])
            for chunk in chunk_batch
        ]

        print(
            "Requesting embeddings for "
            f"{len(texts)} chunks..."
        )

        vectors = (
            await embedding_service
            .embed_documents(texts)
        )

        for chunk, vector in zip(
            chunk_batch,
            vectors,
        ):
            chunk_id = str(
                chunk["chunk_id"]
            )

            await (
                repository
                .persist_chunk_embedding(
                    user_id=user_id,
                    course_id=course_id,
                    canvas_file_id=(
                        canvas_file_id
                    ),
                    chunk_id=chunk_id,
                    embedding=vector,
                    embedding_model=(
                        embedding_service
                        .model
                    ),
                    text_hash=str(
                        chunk["text_hash"]
                    ),
                )
            )

            embedded += 1

            print(
                f"Embedded chunk "
                f"{chunk_id} "
                f"({embedded}/"
                f"{len(pending_chunks)})"
            )

    return {
        "total_chunks": len(chunks),
        "embedded": embedded,
        "skipped": skipped,
        "empty": empty,
    }