# app/core/booking_engine.py
"""
Booking Engine — State Machine for appointment scheduling.

Manages the multi-step booking conversation:
1. Detect booking intent (via intent_detector)
2. Confirm/select service
3. Show available dates
4. Show available time slots
5. Collect patient info (name, RUT)
6. Create booking + Google Calendar event
7. Send confirmation

State is stored in Redis with 30-min TTL.
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta
from enum import Enum
from functools import partial
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.calendar_client import CalendarClient
from app.models.booking import Booking, BookingStatus
from app.models.tenant_calendar import TenantCalendarConfig

logger = logging.getLogger(__name__)
settings = get_settings()


class BookingStep(str, Enum):
    IDLE = "IDLE"
    SELECTING_SERVICE = "SELECTING_SERVICE"
    SELECTING_DATE = "SELECTING_DATE"
    SELECTING_TIME = "SELECTING_TIME"
    COLLECTING_NAME = "COLLECTING_NAME"
    COLLECTING_RUT = "COLLECTING_RUT"
    CONFIRMING = "CONFIRMING"
    BOOKED = "BOOKED"


# Redis key prefix
STATE_PREFIX = "booking_state:"
STATE_TTL = 1800  # 30 minutes

# Slot lock prefix (prevents double booking)
LOCK_PREFIX = "slot_lock:"
LOCK_TTL = 600  # 10 minutes


class BookingEngine:
    """Orchestrates the booking flow as a state machine."""

    async def _get_redis(self) -> aioredis.Redis:
        return aioredis.from_url(
            settings.REDIS_URL, decode_responses=True
        )

    # ==========================================
    # State Management (Redis)
    # ==========================================

    async def get_state(self, conversation_id: UUID) -> dict | None:
        r = await self._get_redis()
        try:
            key = f"{STATE_PREFIX}{conversation_id}"
            data = await r.get(key)
            return json.loads(data) if data else None
        finally:
            await r.aclose()

    async def set_state(self, conversation_id: UUID, state: dict) -> None:
        r = await self._get_redis()
        try:
            key = f"{STATE_PREFIX}{conversation_id}"
            await r.set(key, json.dumps(state, default=str), ex=STATE_TTL)
        finally:
            await r.aclose()

    async def clear_state(self, conversation_id: UUID) -> None:
        r = await self._get_redis()
        try:
            await r.delete(f"{STATE_PREFIX}{conversation_id}")
        finally:
            await r.aclose()

    # ==========================================
    # Slot Locking (Redis)
    # ==========================================

    async def lock_slot(self, tenant_id: UUID, start_time: datetime) -> bool:
        r = await self._get_redis()
        try:
            key = f"{LOCK_PREFIX}{tenant_id}:{start_time.isoformat()}"
            acquired = await r.set(key, "locked", ex=LOCK_TTL, nx=True)
            return bool(acquired)
        finally:
            await r.aclose()

    async def unlock_slot(self, tenant_id: UUID, start_time: datetime) -> None:
        r = await self._get_redis()
        try:
            key = f"{LOCK_PREFIX}{tenant_id}:{start_time.isoformat()}"
            await r.delete(key)
        finally:
            await r.aclose()
    # ==========================================
    # Calendar Operations
    # ==========================================

    async def _get_calendar_client(
        self, db: AsyncSession, tenant_id: UUID
    ) -> tuple[CalendarClient, TenantCalendarConfig] | tuple[None, None]:
        """Get CalendarClient and config for a tenant."""
        result = await db.execute(
            select(TenantCalendarConfig).where(
                TenantCalendarConfig.tenant_id == tenant_id,
                TenantCalendarConfig.is_active == True,
            )
        )
        config = result.scalar_one_or_none()
        if not config:
            return None, None

        client = CalendarClient(
            credentials_json=config.google_credentials_json,
            calendar_id=config.google_calendar_id,
        )
        return client, config

    async def get_available_slots(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        date: datetime,
    ) -> list[dict]:
        """Get available appointment slots for a specific date."""
        cal_client, config = await self._get_calendar_client(db, tenant_id)
        if not cal_client or not config:
            logger.warning(f"No calendar config for tenant {tenant_id}")
            return []

        # Check if date is a working day
        if date.isoweekday() not in config.working_days:
            return []

        # Run sync Google API in thread pool
        loop = asyncio.get_event_loop()
        slots = await loop.run_in_executor(
            None,
            partial(
                cal_client.get_available_slots,
                date=date,
                slot_duration=config.slot_duration_minutes,
                buffer_minutes=config.buffer_between_slots,
                business_start=config.business_hours_start.hour,
                business_end=config.business_hours_end.hour,
                timezone=config.timezone,
            ),
        )
        return slots

    async def create_booking(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        contact_id: UUID,
        conversation_id: UUID,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        patient_name: str,
        patient_rut: str,
        provider_name: str | None = None,
    ) -> Booking | None:
        """
        Create a booking and corresponding Google Calendar event.
        Returns the Booking object or None if failed.
        """
        cal_client, config = await self._get_calendar_client(db, tenant_id)

        # Create Google Calendar event
        google_event = None
        if cal_client and config:
            description = (
                f"Paciente: {patient_name}\n"
                f"RUT: {patient_rut}\n"
                f"Servicio: {service_name}\n"
                f"Agendado vía WhatsApp Bot"
            )

            try:
                loop = asyncio.get_event_loop()
                google_event = await loop.run_in_executor(
                    None,
                    partial(
                        cal_client.create_event,
                        summary=f"{service_name} - {patient_name}",
                        start_time=start_time,
                        end_time=end_time,
                        description=description,
                        timezone=config.timezone,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to create Google Calendar event: {e}")
                # Continue without GCal event — booking still valid

        # Create booking record
        booking = Booking(
            tenant_id=tenant_id,
            contact_id=contact_id,
            conversation_id=conversation_id,
            service_name=service_name,
            provider_name=provider_name,
            start_time=start_time,
            end_time=end_time,
            status=BookingStatus.CONFIRMED,
            patient_name=patient_name,
            patient_rut=patient_rut,
            google_event_id=google_event["id"] if google_event else None,
            google_calendar_id=config.google_calendar_id if config else None,
        )
        db.add(booking)
        await db.commit()
        await db.refresh(booking)

        # Release the slot lock
        await self.unlock_slot(tenant_id, start_time)

        logger.info(
            f"Booking created: {booking.id} for {patient_name} at {start_time}"
        )
        return booking

    # ==========================================
    # State Machine — Process Step
    # ==========================================

    async def process_message(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        contact_id: UUID,
        conversation_id: UUID,
        message: str,
        detected_service: str | None = None,
        detected_date: str | None = None,
        detected_time: str | None = None,
    ) -> dict:
        """
        Process a message in the booking flow.

        Returns:
            {
                "response": str,           # Texto para enviar al paciente
                "booking_active": bool,     # True si el flujo sigue activo
                "booking_completed": bool,  # True si se creó la cita
                "booking": Booking | None,  # El booking si se completó
            }
        """
        state = await self.get_state(conversation_id)

        # New booking flow
        if state is None:
            state = {
                "step": BookingStep.SELECTING_SERVICE,
                "service": detected_service,
                "preferred_date": detected_date,
                "preferred_time": detected_time,
                "selected_slot": None,
                "patient_name": None,
                "patient_rut": None,
            }

        step = BookingStep(state["step"])

        # --- STEP: SELECTING_SERVICE ---
        if step == BookingStep.SELECTING_SERVICE:
            if state.get("service"):
                # Ya tenemos el servicio (vino del intent detector), avanzar
                state["step"] = BookingStep.SELECTING_DATE
                await self.set_state(conversation_id, state)
                return await self._handle_selecting_date(
                    db, tenant_id, conversation_id, state, message
                )
            elif state.get("_asked_service"):
                # Ya preguntamos → este mensaje ES el servicio
                state["service"] = message.strip()
                state["step"] = BookingStep.SELECTING_DATE
                await self.set_state(conversation_id, state)
                return await self._handle_selecting_date(
                    db, tenant_id, conversation_id, state, message
                )
            else:
                # Primera vez → preguntar qué servicio
                state["_asked_service"] = True
                await self.set_state(conversation_id, state)
                return {
                    "response": (
                        "¡Me encantaría ayudarte a agendar! 📅\n\n"
                        "¿Qué servicio te interesa? Por ejemplo:\n"
                        "• Limpieza dental\n"
                        "• Blanqueamiento\n"
                        "• Revisión general"
                    ),
                    "booking_active": True,
                    "booking_completed": False,
                    "booking": None,
                }
        # --- STEP: SELECTING_DATE ---
        if step == BookingStep.SELECTING_DATE:
            # El mensaje es el servicio si no lo teníamos
            if not state.get("service"):
                state["service"] = message.strip()
            return await self._handle_selecting_date(
                db, tenant_id, conversation_id, state, message
            )
        
        # --- STEP: SELECTING_TIME (slot choice) ---
        if step == BookingStep.SELECTING_TIME and state.get("awaiting_slot_choice"):
            # El usuario está respondiendo con su elección de horario
            msg_clean = message.strip()
            if msg_clean.isdigit():
                idx = int(msg_clean) - 1
                slots = state.get("available_slots", [])
                if 0 <= idx < len(slots):
                    state["selected_slot"] = slots[idx]
                    state["step"] = BookingStep.COLLECTING_NAME
                    state["awaiting_slot_choice"] = False
                    await self.set_state(conversation_id, state)
                    return {
                        "response": (
                            "Perfecto, esa hora queda reservada por 10 minutos ⏰\n\n"
                            "¿Cuál es tu nombre completo?"
                        ),
                        "booking_active": True,
                        "booking_completed": False,
                        "booking": None,
                    }

            return {
                "response": "No entendí 🤔 Responde con el número del horario que prefieres.",
                "booking_active": True,
                "booking_completed": False,
                "booking": None,
            }

        # --- STEP: SELECTING_TIME ---
        if step == BookingStep.SELECTING_TIME:
            return await self._handle_selecting_time(
                db, tenant_id, conversation_id, state, message
            )

        # --- STEP: COLLECTING_NAME ---
        if step == BookingStep.COLLECTING_NAME:
            state["patient_name"] = message.strip()
            state["step"] = BookingStep.COLLECTING_RUT
            await self.set_state(conversation_id, state)
            return {
                "response": (
                    f"Perfecto, {state['patient_name']} 👋\n\n"
                    "¿Me puedes dar tu RUT para registrar la hora?"
                ),
                "booking_active": True,
                "booking_completed": False,
                "booking": None,
            }

        # --- STEP: COLLECTING_RUT ---
        if step == BookingStep.COLLECTING_RUT:
            state["patient_rut"] = message.strip()
            state["step"] = BookingStep.CONFIRMING
            await self.set_state(conversation_id, state)
            return await self._handle_confirming(state)

        # --- STEP: CONFIRMING ---
        if step == BookingStep.CONFIRMING:
            return await self._handle_confirmation_response(
                db, tenant_id, contact_id, conversation_id, state, message
            )

        # Default fallback
        return {
            "response": "Disculpa, algo salió mal con el agendamiento. ¿Quieres intentar de nuevo?",
            "booking_active": False,
            "booking_completed": False,
            "booking": None,
        }

    # ==========================================
    # Step Handlers
    # ==========================================

    async def _handle_selecting_date(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        conversation_id: UUID,
        state: dict,
        message: str,
    ) -> dict:
        """Handle date selection step."""
        tz = ZoneInfo("America/Santiago")
        today = datetime.now(tz)

        # Parse preferred date or offer next 3 available days
        target_dates = []
        if state.get("preferred_date"):
            parsed = self._parse_relative_date(state["preferred_date"], today)
            if parsed:
                target_dates = [parsed]

        if not target_dates:
            # Offer next 3 working days
            target_dates = self._next_working_days(today, count=3)

        # Get availability for each date
        date_options = []
        for d in target_dates:
            slots = await self.get_available_slots(db, tenant_id, d)
            if slots:
                date_options.append({
                    "date": d,
                    "slot_count": len(slots),
                })

        if not date_options:
            state["step"] = BookingStep.SELECTING_DATE
            state["preferred_date"] = None
            await self.set_state(conversation_id, state)
            return {
                "response": (
                    "No encontré disponibilidad en los próximos días 😔\n\n"
                    "¿Te gustaría probar con otra fecha? "
                    "Puedes decirme un día específico."
                ),
                "booking_active": True,
                "booking_completed": False,
                "booking": None,
            }

        # Format options
        options_text = ""
        for i, opt in enumerate(date_options, 1):
            day_name = self._format_date_spanish(opt["date"])
            options_text += (
                f"{i}️⃣ {day_name} — {opt['slot_count']} horarios disponibles\n"
            )

        state["step"] = BookingStep.SELECTING_TIME
        state["date_options"] = [
            d["date"].isoformat() for d in date_options
        ]
        await self.set_state(conversation_id, state)

        return {
            "response": (
                f"Para {state['service']}, tengo estas fechas disponibles:\n\n"
                f"{options_text}\n"
                "¿Cuál te acomoda? Responde con el número o el día 📅"
            ),
            "booking_active": True,
            "booking_completed": False,
            "booking": None,
        }

    async def _handle_selecting_time(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        conversation_id: UUID,
        state: dict,
        message: str,
    ) -> dict:
        """Handle time slot selection."""
        tz = ZoneInfo("America/Santiago")

        # Parse user's date choice
        selected_date = None
        msg_clean = message.strip().lower()

        # Try numeric selection (1, 2, 3)
        if msg_clean.isdigit():
            idx = int(msg_clean) - 1
            date_options = state.get("date_options", [])
            if 0 <= idx < len(date_options):
                selected_date = datetime.fromisoformat(date_options[idx])

        # If no date selected yet, try to parse the text
        if not selected_date:
            today = datetime.now(tz)
            selected_date = self._parse_relative_date(msg_clean, today)

        if not selected_date:
            return {
                "response": (
                    "No entendí la fecha 🤔 ¿Puedes decirme el número "
                    "de la opción o el día que prefieres?"
                ),
                "booking_active": True,
                "booking_completed": False,
                "booking": None,
            }

        # Get available slots for selected date
        slots = await self.get_available_slots(db, tenant_id, selected_date)

        if not slots:
            return {
                "response": (
                    f"Ese día no tiene horarios disponibles 😔 "
                    "¿Quieres probar con otro día?"
                ),
                "booking_active": True,
                "booking_completed": False,
                "booking": None,
            }

        # Format time slots
        slots_text = ""
        for i, slot in enumerate(slots[:8], 1):  # Max 8 opciones
            time_str = slot["start"].strftime("%H:%M")
            slots_text += f"{i}️⃣ {time_str}\n"

        day_name = self._format_date_spanish(selected_date)
        state["selected_date"] = selected_date.isoformat()
        state["available_slots"] = [
            {"start": s["start"].isoformat(), "end": s["end"].isoformat()}
            for s in slots[:8]
        ]
        state["step"] = BookingStep.SELECTING_TIME  # stays here until slot picked
        # Override to COLLECTING_NAME step after slot is picked (handled below)
        # Actually we need a sub-state — let's use a flag
        state["awaiting_slot_choice"] = True
        await self.set_state(conversation_id, state)

        return {
            "response": (
                f"Horarios disponibles para {day_name}:\n\n"
                f"{slots_text}\n"
                "¿Cuál hora prefieres? Responde con el número ⏰"
            ),
            "booking_active": True,
            "booking_completed": False,
            "booking": None,
        }

    async def _handle_confirming(self, state: dict) -> dict:
        """Show confirmation summary."""
        slot = state.get("selected_slot", {})
        start = datetime.fromisoformat(slot["start"]) if slot else None
        date_str = self._format_date_spanish(start) if start else "?"
        time_str = start.strftime("%H:%M") if start else "?"

        return {
            "response": (
                f"Perfecto, confirma los datos de tu cita:\n\n"
                f"📋 Servicio: {state.get('service', '?')}\n"
                f"📅 Fecha: {date_str}\n"
                f"⏰ Hora: {time_str}\n"
                f"👤 Nombre: {state.get('patient_name', '?')}\n"
                f"🪪 RUT: {state.get('patient_rut', '?')}\n\n"
                "¿Está todo correcto? Responde *sí* para confirmar o *no* para corregir."
            ),
            "booking_active": True,
            "booking_completed": False,
            "booking": None,
        }

    async def _handle_confirmation_response(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        contact_id: UUID,
        conversation_id: UUID,
        state: dict,
        message: str,
    ) -> dict:
        """Handle yes/no to booking confirmation."""
        msg = message.strip().lower()

        affirmative = {"sí", "si", "yes", "ok", "dale", "sip", "confirmo", "va", "bueno"}
        if any(word in msg for word in affirmative):
            # Create booking!
            slot = state.get("selected_slot", {})
            start_time = datetime.fromisoformat(slot["start"])
            end_time = datetime.fromisoformat(slot["end"])

            booking = await self.create_booking(
                db=db,
                tenant_id=tenant_id,
                contact_id=contact_id,
                conversation_id=conversation_id,
                service_name=state["service"],
                start_time=start_time,
                end_time=end_time,
                patient_name=state["patient_name"],
                patient_rut=state["patient_rut"],
            )

            await self.clear_state(conversation_id)

            if booking:
                date_str = self._format_date_spanish(start_time)
                time_str = start_time.strftime("%H:%M")
                return {
                    "response": (
                        f"¡Tu cita está confirmada! 🎉\n\n"
                        f"📋 {state['service']}\n"
                        f"📅 {date_str} a las {time_str}\n"
                        f"👤 {state['patient_name']}\n\n"
                        "Te enviaremos un recordatorio antes de tu cita. "
                        "Si necesitas cancelar o reagendar, escríbenos con tiempo.\n\n"
                        "¡Te esperamos! 😊"
                    ),
                    "booking_active": False,
                    "booking_completed": True,
                    "booking": booking,
                }
            else:
                return {
                    "response": (
                        "Hubo un problema al crear la cita 😔 "
                        "¿Puedes intentar de nuevo?"
                    ),
                    "booking_active": False,
                    "booking_completed": False,
                    "booking": None,
                }
        else:
            # Cancel or restart
            await self.clear_state(conversation_id)
            return {
                "response": (
                    "Sin problema, cancelé el agendamiento. "
                    "Si quieres agendar después, solo dime 📅"
                ),
                "booking_active": False,
                "booking_completed": False,
                "booking": None,
            }

    # ==========================================
    # Helper Methods
    # ==========================================

    @staticmethod
    def _parse_relative_date(
        text: str, today: datetime
    ) -> datetime | None:
        """Parse natural language dates in Chilean Spanish."""
        text = text.lower().strip()
        mappings = {
            "hoy": 0,
            "mañana": 1,
            "pasado mañana": 2,
        }

        for key, delta in mappings.items():
            if key in text:
                return today + timedelta(days=delta)

        # Day names
        day_names = {
            "lunes": 1, "martes": 2, "miércoles": 3, "miercoles": 3,
            "jueves": 4, "viernes": 5, "sábado": 6, "sabado": 6,
            "domingo": 7,
        }
        for name, isoday in day_names.items():
            if name in text:
                days_ahead = isoday - today.isoweekday()
                if days_ahead <= 0:
                    days_ahead += 7
                return today + timedelta(days=days_ahead)

        return None

    @staticmethod
    def _next_working_days(
        today: datetime,
        count: int = 3,
        working_days: list[int] | None = None,
    ) -> list[datetime]:
        """Get next N working days from today."""
        if working_days is None:
            working_days = [1, 2, 3, 4, 5]

        result = []
        d = today + timedelta(days=1)  # Start from tomorrow
        while len(result) < count:
            if d.isoweekday() in working_days:
                result.append(d)
            d += timedelta(days=1)
        return result

    @staticmethod
    def _format_date_spanish(dt: datetime) -> str:
        """Format date in Chilean Spanish."""
        if dt is None:
            return "?"
        days = {
            1: "Lunes", 2: "Martes", 3: "Miércoles",
            4: "Jueves", 5: "Viernes", 6: "Sábado", 7: "Domingo",
        }
        months = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
        }
        return f"{days[dt.isoweekday()]} {dt.day} de {months[dt.month]}"


# Singleton
booking_engine = BookingEngine()