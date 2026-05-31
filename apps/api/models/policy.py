import enum
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin, pg_enum


class PolicyStatus(enum.StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class Policy(Base, TimestampMixin):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    category: Mapped[str] = mapped_column(String(128), default="")
    owner_department: Mapped[str] = mapped_column(String(256))
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policy_versions.id", use_alter=True, name="fk_policies_current_version_id"),
        nullable=True,
    )


class PolicyVersion(Base, TimestampMixin):
    __tablename__ = "policy_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("policies.id"))
    version_label: Mapped[str] = mapped_column(String(32))
    status: Mapped[PolicyStatus] = mapped_column(pg_enum(PolicyStatus), default=PolicyStatus.ACTIVE)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    markdown_key: Mapped[str] = mapped_column(String(512))
    pdf_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64))
    section_tree: Mapped[dict] = mapped_column(JSONB, default=dict)
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    policy: Mapped["Policy"] = relationship(
        back_populates="versions", foreign_keys=[policy_id]
    )


Policy.versions = relationship(
    "PolicyVersion", back_populates="policy", foreign_keys=[PolicyVersion.policy_id]
)
