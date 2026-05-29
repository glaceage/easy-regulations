import enum
import uuid

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin


class UserRole(enum.StrEnum):
    OWNER = "owner"
    REVIEWER = "reviewer"
    POLICY_ADMIN = "policy_admin"
    READER = "reader"
    SYS_ADMIN = "sys_admin"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(256))
    department: Mapped[str] = mapped_column(String(256), default="")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.READER)
    password_hash: Mapped[str] = mapped_column(String(256), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
