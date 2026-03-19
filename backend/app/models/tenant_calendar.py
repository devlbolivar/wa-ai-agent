# app/models/tenant_calendar.py
"""
Tenant Calendar Configuration.
Stores Google Calendar credentials and settings per tenant.

Para MVP: usamos Service Account (JSON key file).
Para producción: OAuth2 flow completo.
"""

from datetime import datetime, time
from uuid import uuid4

from sqlalchemy import (
    Column, String, DateTime, Boolean, Time, Integer, ForeignKey, Text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.models.base import Base


class TenantCalendarConfig(Base):
    __tablename__ = "tenant_calendar_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
        unique=True,  # Un config por tenant
    )

    # Google Calendar
    google_calendar_id = Column(String(255), nullable=False)  # ej: "primary" o email
    google_credentials_json = Column(Text, nullable=False)     # Service Account JSON

    # Horario del negocio (zona horaria Chile)
    timezone = Column(String(50), default="America/Santiago", nullable=False)
    business_hours_start = Column(Time, default=time(9, 0), nullable=False)   # 09:00
    business_hours_end = Column(Time, default=time(18, 0), nullable=False)    # 18:00
    working_days = Column(
        JSONB,
        default=[1, 2, 3, 4, 5],  # Lun-Vie (isoweekday)
        nullable=False,
    )

    # Config de slots
    slot_duration_minutes = Column(Integer, default=30, nullable=False)
    buffer_between_slots = Column(Integer, default=0, nullable=False)  # minutos entre citas
    max_advance_days = Column(Integer, default=30, nullable=False)     # agendar hasta 30 días

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationship
    tenant = relationship("Tenant", back_populates="calendar_config")