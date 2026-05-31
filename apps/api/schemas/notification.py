import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: uuid.UUID
    message: str
    revision_id: str | None
    policy_id: str | None
    read: bool
    created_at: datetime
