import uuid
from sqlalchemy import String, Integer, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, UUIDMixin, TimestampMixin
from app.models.enums import ConversationStatusEnum, ChannelEnum

class Conversation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    status: Mapped[ConversationStatusEnum | None] = mapped_column(Enum(ConversationStatusEnum))
    channel: Mapped[ChannelEnum | None] = mapped_column(Enum(ChannelEnum))
    source: Mapped[str | None] = mapped_column(String(50))
    lead_score: Mapped[int | None] = mapped_column(Integer) # (0-100)
    escalated_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Relationships
    tenant = relationship("Tenant", back_populates="conversations")
    contact = relationship("Contact", back_populates="conversations")
    agent_assigned = relationship("User", back_populates="escalated_conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="conversation")
