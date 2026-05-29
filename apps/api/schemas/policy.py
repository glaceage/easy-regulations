import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=512)
    owner_department: str = Field(..., min_length=1, max_length=256)
    category: str | None = Field(default=None, max_length=128)


class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title: str
    category: str
    owner_department: str
    current_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
