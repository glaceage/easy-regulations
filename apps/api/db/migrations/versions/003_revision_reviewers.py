"""Add revision_reviewers table.

Revision ID: 003
Revises: 002
Create Date: 2026-05-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revision_reviewers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("assigned_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.String(length=256), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["revisions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "user_id", name="uq_revision_reviewer"),
    )
    op.create_index(
        op.f("ix_revision_reviewers_revision_id"),
        "revision_reviewers",
        ["revision_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_revision_reviewers_revision_id"), table_name="revision_reviewers")
    op.drop_table("revision_reviewers")
