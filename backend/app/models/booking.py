# app/models/booking.py
"""
Booking model.
Represents a scheduled appointment for a tenant.
Status flow: pending → confirmed → completed
                 ↘ cancelled
                 ↘ no_show
"""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Text, Enum as SAEnum, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class BookingStatus(str, enum.Enum):
    PENDING = "pending"          # Slot reservado, esperando confirmación/pago
    CONFIRMED = "confirmed"      # Confirmada (pagó abono o tenant confirma manual)
    CANCELLED = "cancelled"      # Cancelada por paciente o clínica
    COMPLETED = "completed"      # Cita realizada
    NO_SHOW = "no_show"          # Paciente no se presentó


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    contact_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id"),
        nullable=False,
    )
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=True,  # Puede crearse desde dashboard sin conversación
    )

    # Datos de la cita
    service_name = Column(String(200), nullable=False)       # "Blanqueamiento Premium"
    provider_name = Column(String(200), nullable=True)       # "Dra. Martínez"
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    status = Column(
        SAEnum(BookingStatus),
        default=BookingStatus.PENDING,
        nullable=False,
    )

    # Datos del paciente (capturados en el flujo)
    patient_name = Column(String(200), nullable=True)
    patient_rut = Column(String(20), nullable=True)

    # Google Calendar sync
    google_event_id = Column(String(255), nullable=True)     # ID del evento en GCal
    google_calendar_id = Column(String(255), nullable=True)  # Calendar ID usado

    # Metadata
    notes = Column(Text, nullable=True)
    cancelled_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="bookings")
    contact = relationship("Contact", back_populates="bookings")
    conversation = relationship("Conversation", back_populates="bookings")
    payments = relationship("Payment", back_populates="booking")

    __table_args__ = (
        Index("ix_bookings_tenant_start", "tenant_id", "start_time"),
        Index("ix_bookings_tenant_status", "tenant_id", "status"),
    )