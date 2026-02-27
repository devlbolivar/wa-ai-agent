import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP

from app.models.base import Base, UUIDMixin
from app.models.enums import PaymentStatusEnum, PaymentProviderEnum

class Payment(Base, UUIDMixin):
    __tablename__ = "payments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), index=True)
    
    amount: Mapped[int | None] = mapped_column(Integer) # CLP cents
    currency: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[PaymentStatusEnum | None] = mapped_column(Enum(PaymentStatusEnum))
    provider: Mapped[PaymentProviderEnum | None] = mapped_column(Enum(PaymentProviderEnum))
    provider_payment_id: Mapped[str | None] = mapped_column(String(100))
    payment_link_url: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Relationships
    tenant = relationship("Tenant", back_populates="payments")
    booking = relationship("Booking", back_populates="payments")
    contact = relationship("Contact", back_populates="payments")
