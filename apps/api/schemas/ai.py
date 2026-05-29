import uuid

from pydantic import BaseModel

from apps.api.models.llm_suggestion import LlmSuggestionAction, LlmSuggestionStatus


class DraftJobResponse(BaseModel):
    job_id: str


class LlmSuggestionResponse(BaseModel):
    id: uuid.UUID
    revision_id: uuid.UUID
    section_id: str
    action: LlmSuggestionAction
    suggested_markdown: str
    rationale: str
    status: LlmSuggestionStatus
    model_name: str
    input_hash: str

    model_config = {"from_attributes": True}
