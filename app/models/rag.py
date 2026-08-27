from pydantic import BaseModel, Field


class RagAnswerRequest(BaseModel):
    user_id: str = Field(
        min_length=1,
        max_length=200,
    )
    course_id: str = Field(
        min_length=1,
        max_length=200,
    )
    question: str = Field(
        min_length=1,
        max_length=8000,
    )
    source_limit: int | None = Field(
        default=None,
        ge=1,
        le=20,
    )


class RagSourceResponse(BaseModel):
    source_number: int
    chunk_id: str
    document_path: str
    canvas_file_id: str
    filename: str
    page_number: int | None
    chunk_index: int | None
    similarity: float
    distance: float


class RagAnswerResponse(BaseModel):
    question: str
    answer: str
    generation_model: str
    sources: list[RagSourceResponse]