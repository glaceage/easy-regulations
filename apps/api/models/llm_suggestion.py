import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin


class LlmSuggestionStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class LlmSuggestionAction(enum.StrEnum):
    REPLACE = "replace"
    INSERT = "insert"
    DELETE = "delete"


class LlmSuggestion(Base, TimestampMixin):
    __tablename__ = "llm_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("revisions.id"), index=True
    )
    section_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[LlmSuggestionAction] = mapped_column(Enum(LlmSuggestionAction))
    suggested_markdown: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[LlmSuggestionStatus] = mapped_column(
        Enum(LlmSuggestionStatus), default=LlmSuggestionStatus.PENDING
    )
    model_name: Mapped[str] = mapped_column(String(128), default="")
    input_hash: Mapped[str] = mapped_column(String(64), default="")
