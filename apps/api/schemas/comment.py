import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.api.models.comment import CommentStatus


class CommentCreate(BaseModel):
    section_id: str = Field(max_length=64)
    body: str


class CommentUpdate(BaseModel):
    status: CommentStatus | None = None
    resolution_note: str | None = None


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    revision_id: uuid.UUID
    section_id: str
    author_id: uuid.UUID
    body: str
    status: CommentStatus
    resolution_note: str | None
    is_mandatory_reviewer: bool
    created_at: datetime
    updated_at: datetime
