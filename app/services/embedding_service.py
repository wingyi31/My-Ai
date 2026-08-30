from __future__ import annotations

from google import genai
from google.genai import types


_RETRYABLE_STATUS_CODES = [
    408,
    429,
    500,
    502,
    503,
    504,
]


class VertexEmbeddingService:

    def __init__(
        self,
        *,
        project_id: str,
        location: str = "global",
        model: str = "gemini-embedding-001",
        dimensions: int = 768,
    ) -> None:
        if not 1 <= dimensions <= 2048:
            raise ValueError(
                "Embedding dimensions must be "
                "between 1 and 2048"
            )

        self.model = model
        self.dimensions = dimensions

        retry_options = (
            types.HttpRetryOptions(
                # Includes the initial request.
                attempts=7,
                initial_delay=2.0,
                max_delay=60.0,
                exp_base=2.0,
                jitter=1.0,
                http_status_codes=(
                    _RETRYABLE_STATUS_CODES
                ),
            )
        )

        self._client = genai.Client(
            enterprise=True,
            project=project_id,
            location=location,
            http_options=types.HttpOptions(
                api_version="v1",
                retry_options=retry_options,
            ),
        ).aio

    async def embed_document(
        self,
        text: str,
        *,
        title: str | None = None,
    ) -> list[float]:
        vectors = await self._embed_many(
            texts=[text],
            task_type=(
                "RETRIEVAL_DOCUMENT"
            ),
            title=title,
        )

        return vectors[0]

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return await self._embed_many(
            texts=texts,
            task_type=(
                "RETRIEVAL_DOCUMENT"
            ),
        )

    async def embed_query(
        self,
        text: str,
    ) -> list[float]:
        vectors = await self._embed_many(
            texts=[text],
            task_type="RETRIEVAL_QUERY",
        )

        return vectors[0]

    async def _embed_many(
        self,
        *,
        texts: list[str],
        task_type: str,
        title: str | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        cleaned_texts = [
            text.strip()
            for text in texts
        ]

        if any(
            not text
            for text in cleaned_texts
        ):
            raise ValueError(
                "Cannot generate embeddings "
                "for empty text"
            )

        if title is None:
            config = (
                types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=(
                        self.dimensions
                    ),
                )
            )
        else:
            config = (
                types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=(
                        self.dimensions
                    ),
                    title=title,
                )
            )

        response = await (
            self._client
            .models
            .embed_content(
                model=self.model,
                contents=cleaned_texts,
                config=config,
            )
        )

        response_embeddings = (
            response.embeddings or []
        )

        if (
            len(response_embeddings)
            != len(cleaned_texts)
        ):
            raise RuntimeError(
                "Unexpected embedding count: "
                f"expected {len(cleaned_texts)}, "
                f"received "
                f"{len(response_embeddings)}"
            )

        vectors: list[
            list[float]
        ] = []

        for response_embedding in (
            response_embeddings
        ):
            values = (
                response_embedding.values
            )

            if values is None:
                raise RuntimeError(
                    "Embedding contains "
                    "no vector values"
                )

            vector = [
                float(value)
                for value in values
            ]

            if (
                len(vector)
                != self.dimensions
            ):
                raise RuntimeError(
                    "Unexpected embedding "
                    "dimension: "
                    f"expected "
                    f"{self.dimensions}, "
                    f"received {len(vector)}"
                )

            vectors.append(vector)

        return vectors

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(
        self,
    ) -> "VertexEmbeddingService":
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        await self.close()