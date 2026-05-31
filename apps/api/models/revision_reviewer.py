import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin


class RevisionReviewer(Base, TimestampMixin):
    __tablename__ = "revision_reviewers"
    __table_args__ = (UniqueConstraint("revision_id", "user_id", name="uq_revision_reviewer"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("revisions.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str] = mapped_column(String(256), default="")
