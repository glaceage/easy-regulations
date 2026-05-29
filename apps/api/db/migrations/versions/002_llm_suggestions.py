"""Add llm_suggestions table.

Revision ID: 002
Revises: 001
Create Date: 2026-05-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

llm_suggestion_status_enum = postgresql.ENUM(
    "pending",
    "accepted",
    "rejected",
    name="llmsuggestionstatus",
    create_type=False,
)
llm_suggestion_action_enum = postgresql.ENUM(
    "replace",
    "insert",
    "delete",
    name="llmsuggestionaction",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    llm_suggestion_status_enum.create(bind, checkfirst=True)
    llm_suggestion_action_enum.create(bind, checkfirst=True)

    op.create_table(
        "llm_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", sa.String(length=64), nullable=False),
        sa.Column("action", llm_suggestion_action_enum, nullable=False),
        sa.Column("suggested_markdown", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", llm_suggestion_status_enum, nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
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
        sa.ForeignKeyConstraint(["revision_id"], ["revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_llm_suggestions_revision_id"),
        "llm_suggestions",
        ["revision_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_suggestions_revision_id"), table_name="llm_suggestions")
    op.drop_table("llm_suggestions")

    bind = op.get_bind()
    llm_suggestion_action_enum.drop(bind, checkfirst=True)
    llm_suggestion_status_enum.drop(bind, checkfirst=True)
