"""
WhatsApp Cloud API Client.
Handles sending messages via Meta's Graph API.
"""

import httpx
import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class WhatsAppClient:
    """Client for WhatsApp Cloud API message operations."""

    def __init__(self, phone_number_id: Optional[str] = None):
        # We don't store headers or tokens here so they are dynamically read 
        # from the latest settings on every request.
        pass

    @property
    def base_url(self):
        return get_settings().whatsapp_api_url

    @property
    def default_phone_number_id(self):
        return get_settings().whatsapp_phone_number_id

    def get_headers(self) -> dict:
        """Dynamically get headers so we always use the freshest token."""
        token = get_settings().WHATSAPP_ACCESS_TOKEN
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_messages_url(self, phone_number_id: Optional[str] = None) -> str:
        """Get the URL for sending messages, optionally overriding the phone number ID."""
        target_phone_id = phone_number_id or self.default_phone_number_id
        return f"{self.base_url}/{target_phone_id}/messages"

    async def send_text_message(
        self,
        to: str,
        body: str,
        preview_url: bool = False,
        phone_number_id: Optional[str] = None,
    ) -> dict:
        """
        Send a text message to a WhatsApp number.

        Args:
            to: Recipient phone number with country code (e.g., "56912345678")
            body: Message text content
            preview_url: Whether to show URL previews in the message

        Returns:
            API response dict with message ID
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": body,
            },
        }

        return await self._send_request(
            payload, 
            phone_number_id=phone_number_id,
        )

    async def send_reply(
        self,
        to: str,
        body: str,
        message_id: str,
        phone_number_id: Optional[str] = None,
    ) -> dict:
        """
        Send a reply to a specific message (shows as quoted reply in WhatsApp).

        Args:
            to: Recipient phone number
            body: Reply text content
            message_id: The wa_message_id to reply to
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "context": {
                "message_id": message_id,
            },
            "text": {
                "body": body,
            },
        }

        return await self._send_request(
            payload, 
            phone_number_id=phone_number_id,
        )

    async def mark_as_read(
        self, 
        message_id: str, 
        phone_number_id: Optional[str] = None,
    ) -> dict:
        """
        Mark a message as read (shows blue checkmarks).

        Args:
            message_id: The WhatsApp message ID to mark as read
        """
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        return await self._send_request(
            payload, 
            phone_number_id=phone_number_id,
        )

    async def send_interactive_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict],
        header: Optional[str] = None,
        footer: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> dict:
        """
        Send a message with interactive buttons (max 3 buttons).

        Args:
            to: Recipient phone number
            body: Main message text
            buttons: List of dicts with "id" and "title" keys
            header: Optional header text
            footer: Optional footer text

        Example:
            buttons = [
                {"id": "btn_yes", "title": "Sí, agendar"},
                {"id": "btn_no", "title": "No, gracias"},
            ]
        """
        action_buttons = [
            {
                "type": "reply",
                "reply": {"id": btn["id"], "title": btn["title"]},
            }
            for btn in buttons[:3]  # WhatsApp max 3 buttons
        ]

        interactive = {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": action_buttons},
        }

        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }

        return await self._send_request(
            payload, 
            phone_number_id=phone_number_id,
        )

    async def _send_request(
        self, 
        payload: dict, 
        phone_number_id: Optional[str] = None,
    ) -> dict:
        """Send a request to the WhatsApp Cloud API."""
        url = self.get_messages_url(phone_number_id)
        
        # Remove phone_number_id from payload if it exists (it's only for routing)
        if "phone_number_id" in payload:
            del payload["phone_number_id"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    url,
                    headers=self.get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                logger.info(
                    "WhatsApp message sent",
                    extra={
                        "to": payload.get("to"),
                        "type": payload.get("type"),
                        "wa_message_id": data.get("messages", [{}])[0].get("id"),
                    },
                )

                return data

            except httpx.HTTPStatusError as e:
                logger.error(
                    "WhatsApp API error",
                    extra={
                        "status_code": e.response.status_code,
                        "response": e.response.text,
                        "to": payload.get("to"),
                    },
                )
                raise

            except httpx.RequestError as e:
                logger.error(f"WhatsApp request failed: {e}")
                raise


# Singleton instance
whatsapp_client = WhatsAppClient()