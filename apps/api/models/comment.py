import enum
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, pg_enum


class CommentStatus(enum.StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class Comment(Base, TimestampMixin):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("revisions.id"))
    section_id: Mapped[str] = mapped_column(String(64))
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[CommentStatus] = mapped_column(pg_enum(CommentStatus), default=CommentStatus.OPEN)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_suggestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_mandatory_reviewer: Mapped[bool] = mapped_column(default=True)
