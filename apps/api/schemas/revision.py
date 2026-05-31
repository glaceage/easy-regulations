import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.api.models.revision import RevisionState


class RevisionCreate(BaseModel):
    policy_id: uuid.UUID
    change_brief: str = ""
    target_version_label: str | None = Field(default=None, max_length=32)


class RevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_id: uuid.UUID
    base_version_id: uuid.UUID
    owner_user_id: uuid.UUID
    state: RevisionState
    change_brief: str
    draft_markdown_key: str
    draft_content_sha256: str
    target_version_label: str
    created_at: datetime
    updated_at: datetime


class RevisionMetaUpdate(BaseModel):
    change_brief: str | None = Field(default=None, max_length=2000)
    target_version_label: str | None = Field(default=None, max_length=32)


class TransitionRequest(BaseModel):
    target_state: RevisionState


class DraftMarkdownResponse(BaseModel):
    markdown: str
    content_sha256: str


class DraftMarkdownUpdate(BaseModel):
    markdown: str


class PublishResponse(BaseModel):
    revision_id: uuid.UUID
    state: RevisionState
    policy_version_id: uuid.UUID
    version_label: str
    pdf_key: str
    markdown_key: str
