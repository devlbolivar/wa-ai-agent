import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP

from app.models.base import Base, UUIDMixin
from app.models.enums import UserRoleEnum

class User(Base, UUIDMixin):
    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRoleEnum | None] = mapped_column(Enum(UserRoleEnum))
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    escalated_conversations = relationship("Conversation", back_populates="agent_assigned")
