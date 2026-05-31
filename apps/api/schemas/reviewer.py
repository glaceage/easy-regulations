import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FeedbackStatus = Literal["awaiting", "optional", "submitted", "closed"]


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
    comment_count: int = 0
    feedback_status: FeedbackStatus = "awaiting"


class ReviewAssignmentResponse(BaseModel):
    assignment_id: uuid.UUID
    revision_id: uuid.UUID
    policy_id: uuid.UUID
    policy_code: str
    policy_title: str
    revision_state: str
    target_version_label: str
    change_brief: str
    is_mandatory: bool
    assigned_at: datetime
    my_comment_count: int
    feedback_status: FeedbackStatus
