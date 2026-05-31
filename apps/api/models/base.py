import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def pg_enum(enum_cls: type[enum.StrEnum]) -> Enum:
    """Map StrEnum values (e.g. policy_admin) to PostgreSQL ENUM labels."""
    return Enum(enum_cls, values_callable=lambda members: [member.value for member in members])


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
