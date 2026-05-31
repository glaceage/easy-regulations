import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewerAssignRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    is_mandatory: bool = True
    note: str = ""


class ReviewerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    revision_id: uuid.UUID
    user_id: uuid.UUID
    username: str
    display_name: str
    is_mandatory: bool
    note: str
    created_at: datetime
