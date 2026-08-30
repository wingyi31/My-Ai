from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    status,
)

from app.core.config import get_settings
from app.models.rag import (
    RagAnswerRequest,
    RagAnswerResponse,
    RagSourceResponse,
)
from app.services.rag_answer_service import (
    RagAnswerService,
)


router = APIRouter(
    prefix="/api/v1/rag",
    tags=["rag"],
)


def get_rag_service(
    request: Request,
) -> RagAnswerService:
    service = getattr(
        request.app.state,
        "rag_answer_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "RAG answer service is not ready"
            ),
        )

    return service


@router.post(
    "/answer",
    response_model=RagAnswerResponse,
)
async def answer_course_question(
    payload: RagAnswerRequest,
    request: Request,
) -> RagAnswerResponse:
    service = get_rag_service(request)
    settings = get_settings()

    source_limit = (
        payload.source_limit
        if payload.source_limit is not None
        else settings.rag_default_source_limit
    )

    try:
        result = (
            await service.answer_course_question(
                user_id=payload.user_id,
                course_id=payload.course_id,
                question=payload.question,
                source_limit=source_limit,
            )
        )
    except ValueError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(error),
        ) from error

    sources = [
        RagSourceResponse(
            source_number=source_number,
            chunk_id=source.chunk_id,
            document_path=(
                source.document_path
            ),
            canvas_file_id=(
                source.canvas_file_id
            ),
            filename=source.filename,
            page_number=source.page_number,
            chunk_index=source.chunk_index,
            similarity=source.similarity,
            distance=source.distance,
        )
        for source_number, source in enumerate(
            result.sources,
            start=1,
        )
    ]

    return RagAnswerResponse(
        question=result.question,
        answer=result.answer,
        generation_model=(
            result.generation_model
        ),
        sources=sources,
    )