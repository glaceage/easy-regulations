import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin


class RevisionState(enum.StrEnum):
    DRAFT = "draft"
    IN_CONSULTATION = "in_consultation"
    IN_REVISION = "in_revision"
    PENDING_PUBLISH = "pending_publish"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[RevisionState, set[RevisionState]] = {
    RevisionState.DRAFT: {RevisionState.IN_CONSULTATION, RevisionState.CANCELLED},
    RevisionState.IN_CONSULTATION: {
        RevisionState.IN_REVISION,
        RevisionState.IN_CONSULTATION,
        RevisionState.CANCELLED,
    },
    RevisionState.IN_REVISION: {
        RevisionState.IN_CONSULTATION,
        RevisionState.PENDING_PUBLISH,
        RevisionState.CANCELLED,
    },
    RevisionState.PENDING_PUBLISH: {RevisionState.PUBLISHED, RevisionState.CANCELLED},
    RevisionState.PUBLISHED: set(),
    RevisionState.CANCELLED: set(),
}


def can_transition(current: RevisionState, target: RevisionState) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


class Revision(Base, TimestampMixin):
    __tablename__ = "revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("policies.id"))
    base_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_versions.id")
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    state: Mapped[RevisionState] = mapped_column(Enum(RevisionState), default=RevisionState.DRAFT)
    change_brief: Mapped[str] = mapped_column(Text, default="")
    draft_markdown_key: Mapped[str] = mapped_column(String(512))
    draft_content_sha256: Mapped[str] = mapped_column(String(64), default="")
    target_version_label: Mapped[str] = mapped_column(String(32), default="")
