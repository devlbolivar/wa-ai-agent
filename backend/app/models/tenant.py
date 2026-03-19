import uuid
from sqlalchemy import String, Text, Enum, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base, UUIDMixin, TimestampMixin
from app.models.enums import PaymentProviderEnum, PlanEnum

class Tenant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    wa_phone_number_id: Mapped[str | None] = mapped_column(String(50))
    wa_access_token: Mapped[str | None] = mapped_column(Text)
    google_oauth_token: Mapped[dict | None] = mapped_column(JSONB)
    payment_provider: Mapped[PaymentProviderEnum | None] = mapped_column(Enum(PaymentProviderEnum))
    payment_account_id: Mapped[str | None] = mapped_column(String(100))
    plan: Mapped[PlanEnum | None] = mapped_column(Enum(PlanEnum))
    settings: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True)
    # Relationships
    contacts = relationship("Contact", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="tenant", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="tenant", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="tenant", lazy="selectin")
    calendar_config = relationship(
        "TenantCalendarConfig",
        back_populates="tenant",
        uselist=False,  # One-to-one
        lazy="selectin",
    )
    payments = relationship("Payment", back_populates="tenant", cascade="all, delete-orphan")
    knowledge_bases = relationship("KnowledgeBase", back_populates="tenant", cascade="all, delete-orphan")
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
