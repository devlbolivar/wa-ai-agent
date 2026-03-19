# app/core/calendar_client.py
"""
Google Calendar client.
Wraps the Google Calendar API for availability checks and event management.
Uses Service Account authentication (MVP).
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarClient:
    """Wrapper for Google Calendar API operations."""

    def __init__(self, credentials_json: str, calendar_id: str):
        """
        Args:
            credentials_json: Service Account JSON string (from tenant config)
            calendar_id: Google Calendar ID (usually an email or "primary")
        """
        creds_data = json.loads(credentials_json)
        credentials = Credentials.from_service_account_info(
            creds_data, scopes=SCOPES
        )
        self.service = build("calendar", "v3", credentials=credentials)
        self.calendar_id = calendar_id

    def get_busy_slots(
        self,
        date: datetime,
        timezone: str = "America/Santiago",
    ) -> list[dict]:
        """
        Get all busy time ranges for a specific date.

        Returns:
            List of {"start": datetime, "end": datetime} for occupied slots.
        """
        tz = ZoneInfo(timezone)
        day_start = datetime(date.year, date.month, date.day, 0, 0, tzinfo=tz)
        day_end = day_start + timedelta(days=1)

        body = {
            "timeMin": day_start.isoformat(),
            "timeMax": day_end.isoformat(),
            "timeZone": timezone,
            "items": [{"id": self.calendar_id}],
        }

        result = self.service.freebusy().query(body=body).execute()
        busy = result["calendars"][self.calendar_id]["busy"]

        return [
            {
                "start": datetime.fromisoformat(slot["start"]),
                "end": datetime.fromisoformat(slot["end"]),
            }
            for slot in busy
        ]

    def get_available_slots(
        self,
        date: datetime,
        slot_duration: int = 30,
        buffer_minutes: int = 0,
        business_start: int = 9,   # hora inicio (24h)
        business_end: int = 18,    # hora fin (24h)
        timezone: str = "America/Santiago",
    ) -> list[dict]:
        """
        Calculate available appointment slots for a date.

        Returns:
            List of {"start": datetime, "end": datetime} for free slots.
        """
        tz = ZoneInfo(timezone)
        busy = self.get_busy_slots(date, timezone)

        # Generate all possible slots within business hours
        available = []
        current = datetime(
            date.year, date.month, date.day,
            business_start, 0, tzinfo=tz,
        )
        end_of_day = datetime(
            date.year, date.month, date.day,
            business_end, 0, tzinfo=tz,
        )

        # Don't show slots in the past
        now = datetime.now(tz)
        if current < now:
            # Round up to next slot boundary
            minutes_past = (now - current).total_seconds() / 60
            slots_past = int(minutes_past // (slot_duration + buffer_minutes)) + 1
            current += timedelta(
                minutes=slots_past * (slot_duration + buffer_minutes)
            )

        while current + timedelta(minutes=slot_duration) <= end_of_day:
            slot_end = current + timedelta(minutes=slot_duration)

            # Check if this slot overlaps with any busy period
            is_free = True
            for b in busy:
                # Overlap: slot starts before busy ends AND slot ends after busy starts
                if current < b["end"] and slot_end > b["start"]:
                    is_free = False
                    break

            if is_free:
                available.append({
                    "start": current,
                    "end": slot_end,
                })

            current += timedelta(minutes=slot_duration + buffer_minutes)

        return available

    def create_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        description: str = "",
        timezone: str = "America/Santiago",
        attendee_phone: Optional[str] = None,
    ) -> dict:
        """
        Create a calendar event.

        Returns:
            Google Calendar event resource (dict with 'id', 'htmlLink', etc.)
        """
        event = {
            "summary": summary,
            "description": description,
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": timezone,
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 60 * 24},  # 24 hrs antes
                    {"method": "popup", "minutes": 120},       # 2 hrs antes
                ],
            },
        }

        if description:
            event["description"] = description

        result = (
            self.service.events()
            .insert(calendarId=self.calendar_id, body=event)
            .execute()
        )

        logger.info(
            f"Created event {result['id']} at {start_time} on {self.calendar_id}"
        )
        return result

    def cancel_event(self, event_id: str) -> bool:
        """Cancel (delete) a calendar event."""
        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id,
            ).execute()
            logger.info(f"Cancelled event {event_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel event {event_id}: {e}")
            return False