import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, ARRAY

from app.models.base import Base, UUIDMixin
from app.models.enums import BookingStatusEnum

class Booking(Base, UUIDMixin):
    __tablename__ = "bookings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"))
    
    service: Mapped[str | None] = mapped_column(String(200))
    professional: Mapped[str | None] = mapped_column(String(200))
    datetime: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_min: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[BookingStatusEnum | None] = mapped_column(Enum(BookingStatusEnum))
    google_event_id: Mapped[str | None] = mapped_column(String(100))
    reminder_sent: Mapped[list[bool] | None] = mapped_column(ARRAY(Boolean))

    # Relationships
    tenant = relationship("Tenant", back_populates="bookings")
    contact = relationship("Contact", back_populates="bookings")
    conversation = relationship("Conversation", back_populates="bookings")
    payments = relationship("Payment", back_populates="booking")
