import uuid
from sqlalchemy import String, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, UUIDMixin, TimestampMixin
from app.models.enums import LeadStatusEnum

class Contact(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "contacts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(200))
    rut: Mapped[str | None] = mapped_column(String(12))
    email: Mapped[str | None] = mapped_column(String(200))
    lead_status: Mapped[LeadStatusEnum | None] = mapped_column(Enum(LeadStatusEnum))
    source: Mapped[str | None] = mapped_column(String(50))
    metadata_data: Mapped[dict | None] = mapped_column("metadata", JSONB) 

    # Relationships
    tenant = relationship("Tenant", back_populates="contacts")
    conversations = relationship("Conversation", back_populates="contact", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="contact", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="contact", cascade="all, delete-orphan")
