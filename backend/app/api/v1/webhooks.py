"""
WhatsApp Webhook Endpoints — Week 3.
Now dispatches messages to Celery for async processing with debounce.
The webhook returns 200 immediately; AI processing happens in the worker.
"""

import logging

from fastapi import APIRouter, Query, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.core.database import get_db
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    """Meta webhook verification challenge."""
    if hub_mode == "subscribe" and hub_token == settings.whatsapp_verify_token:
        logger.info("Webhook verified successfully")
        return int(hub_challenge)

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def receive_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receive incoming WhatsApp messages.
    Extracts message data and dispatches to Celery via debounce buffer.
    Returns 200 immediately — processing is async.
    """
    body = await request.json()

    try:
        entry = body.get("entry", [])
        if not entry:
            return {"status": "ok"}

        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ok"}

        value = changes[0].get("value", {})

        # 1. Identify tenant from phone_number_id
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id")
        
        if not phone_number_id:
            logger.warning("No phone_number_id found in webhook payload")
            return {"status": "ok"}

        result = await db.execute(select(Tenant).where(Tenant.wa_phone_number_id == phone_number_id))
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            logger.warning(f"Unknown phone_number_id: {phone_number_id}, ignoring messages.")
            return {"status": "ok"}
            
        tenant_id = tenant.id

        # Handle incoming messages → dispatch to Celery
        messages = value.get("messages", [])
        for msg in messages:
            _dispatch_message(msg, tenant_id)

        # Handle status updates (no async processing needed)
        statuses = value.get("statuses", [])
        for status in statuses:
            _handle_status_update(status)

    except Exception as e:
        # Always return 200 to Meta
        logger.exception(f"Error processing webhook: {e}")

    return {"status": "ok"}


def _dispatch_message(msg: dict, tenant_id):
    """
    Extract message data and push to debounce buffer.
    The Celery task will pick it up after the debounce window.
    """
    from app.workers.message_tasks import buffer_message

    msg_type = msg.get("type", "")
    sender_phone = msg.get("from", "")
    wa_message_id = msg.get("id", "")

    # Extract text based on message type
    text = _extract_text(msg, msg_type)

    logger.info(f"Dispatching message from {sender_phone}: {text[:80]}...")

    # Push to debounce buffer → Celery processes after 4 seconds
    buffer_message(
        tenant_id=str(tenant_id) if tenant_id else "",
        contact_phone=sender_phone,
        message_data={
            "text": text,
            "msg_type": msg_type,
            "wa_message_id": wa_message_id,
        },
    )


def _extract_text(msg: dict, msg_type: str) -> str:
    """Extract readable text from any WhatsApp message type."""
    if msg_type == "text":
        return msg.get("text", {}).get("body", "")

    if msg_type == "interactive":
        interactive = msg.get("interactive", {})
        if interactive.get("type") == "button_reply":
            return interactive.get("button_reply", {}).get("title", "")
        if interactive.get("type") == "list_reply":
            return interactive.get("list_reply", {}).get("title", "")
        return "[interactive message]"

    type_labels = {
        "image": "[Imagen recibida]",
        "audio": "[Audio recibido]",
        "document": "[Documento recibido]",
        "location": "[Ubicación recibida]",
        "sticker": "[Sticker recibido]",
        "video": "[Video recibido]",
    }
    return type_labels.get(msg_type, f"[{msg_type} message]")


def _handle_status_update(status: dict):
    """Log message delivery status."""
    status_type = status.get("status")
    if status_type in ("delivered", "read"):
        logger.debug(f"Message {status_type}: to={status.get('recipient_id')}")