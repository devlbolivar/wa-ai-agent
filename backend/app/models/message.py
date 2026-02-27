import uuid
from sqlalchemy import String, Text, Integer, Float, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, UUIDMixin, TimestampMixin
from app.models.enums import RoleEnum, MessageTypeEnum

class Message(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    role: Mapped[RoleEnum | None] = mapped_column(Enum(RoleEnum))
    content: Mapped[str | None] = mapped_column(Text)
    message_type: Mapped[MessageTypeEnum | None] = mapped_column(Enum(MessageTypeEnum))
    wa_message_id: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float | None] = mapped_column(Float)
    tokens_used: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    tenant = relationship("Tenant", back_populates="messages")
