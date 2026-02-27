"""
WhatsApp Webhook Endpoints.
Handles Meta's verification challenge and incoming messages.
"""

import hashlib
import hmac
import logging
from uuid import uuid4

from fastapi import APIRouter, Query, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.whatsapp_client import whatsapp_client
from app.core.database import get_db
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.tenant import Tenant
from sqlalchemy import select
logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/webhook", tags=["webhooks"])


# ============================================
# GET — Meta Verification Challenge
# ============================================
@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    """
    Meta sends a GET request to verify your webhook URL.
    Must return the hub.challenge value if the verify_token matches.
    """
    if hub_mode == "subscribe" and hub_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return int(hub_challenge)

    logger.warning(f"Webhook verification failed: mode={hub_mode}")
    raise HTTPException(status_code=403, detail="Verification failed")


# ============================================
# POST — Receive Incoming Messages
# ============================================
@router.post("/whatsapp")
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receives incoming WhatsApp messages and status updates.
    Meta sends a POST with the message payload.
    """
    body = await request.json()

    # Verify webhook signature (optional but recommended)
    # _verify_signature(request, body)
    try:
        # Navigate the Meta webhook payload structure
        entry = body.get("entry", [])
        if not entry:
            return {"status": "ok"}

        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ok"}

        value = changes[0].get("value", {})

        # Get the phone_number_id that received this message (identifies the tenant)
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id", "")

        if not phone_number_id:
            logger.warning("No phone_number_id found in webhook payload.")
            return {"status": "ok"}
            
        # Resolve tenant right here!
        result = await db.execute(select(Tenant).where(Tenant.wa_phone_number_id == phone_number_id))
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            logger.warning(f"No tenant found for phone_number_id={phone_number_id}")
            return {"status": "ok"}
            
        tenant_id = tenant.id

        # Handle incoming messages
        messages = value.get("messages", [])
        for msg in messages:
            await _handle_incoming_message(db, msg, phone_number_id, tenant_id)

        # Handle status updates (sent, delivered, read)
        statuses = value.get("statuses", [])
        for status in statuses:
            await _handle_status_update(db, status)

    except Exception as e:
        # Always return 200 to Meta, even on errors
        # Otherwise Meta will retry and flood your server
        logger.exception(f"Error processing webhook: {e}")

    return {"status": "ok"}


async def _handle_status_update(db: AsyncSession, status: dict):
    """Log status updates received from Meta."""
    # In Week 4/7 we will update the Message table with this status
    status_type = status.get("status")
    msg_id = status.get("id")
    logger.info(f"Message {msg_id} status: {status_type}")


# ============================================
# Message Handler
# ============================================
async def _handle_incoming_message(
    db: AsyncSession,
    msg: dict,
    phone_number_id: str,
    tenant_id,
):
    """
    Process a single incoming WhatsApp message.
    For Week 2: echo bot — just reply back.
    """
    msg_type = msg.get("type")
    sender_phone = msg.get("from", "")
    wa_message_id = msg.get("id", "")
    timestamp = msg.get("timestamp", "")

    # Extract message text based on type
    if msg_type == "text":
        text = msg.get("text", {}).get("body", "")
    elif msg_type == "interactive":
        # Button reply or list reply
        interactive = msg.get("interactive", {})
        if interactive.get("type") == "button_reply":
            text = interactive.get("button_reply", {}).get("title", "")
        elif interactive.get("type") == "list_reply":
            text = interactive.get("list_reply", {}).get("title", "")
        else:
            text = "[interactive message]"
    elif msg_type == "image":
        text = "[Imagen recibida]"
    elif msg_type == "audio":
        text = "[Audio recibido]"
    elif msg_type == "document":
        text = "[Documento recibido]"
    elif msg_type == "location":
        text = "[Ubicación recibida]"
    else:
        text = f"[{msg_type} message]"

    logger.info(
        "Message received",
        extra={
            "from": sender_phone,
            "type": msg_type,
            "text": text[:100],
            "wa_message_id": wa_message_id,
        },
    )

    # ----- Save to DB -----

    # 1. Find or create contact
    contact = await _get_or_create_contact(db, sender_phone, tenant_id)

    # 2. Find or create active conversation
    conversation = await _get_or_create_conversation(db, contact.id, tenant_id)

    # 3. Save the incoming message
    incoming_msg = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        tenant_id=conversation.tenant_id,
        role="user",
        content=text,
        message_type=msg_type or "text",
        wa_message_id=wa_message_id,
    )
    db.add(incoming_msg)

    # ----- Mark as read -----
    await whatsapp_client.mark_as_read(
        message_id=wa_message_id, 
        phone_number_id=phone_number_id
    )

    # ----- Generate response -----
    # Week 2: Simple echo bot
    # Week 3: This will be replaced with AI Engine + RAG
    response_text = _generate_echo_response(text, contact.name)

    # ----- Send response -----
    # In this shared-token architecture, we pass the phone_number_id so the client
    # knows which phone number to send the message FROM.
    result = await whatsapp_client.send_text_message(
        to=sender_phone,
        body=response_text,
        phone_number_id=phone_number_id
    )

    # Save bot response to DB
    bot_wa_id = result.get("messages", [{}])[0].get("id", "")
    bot_msg = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        tenant_id=conversation.tenant_id,
        role="bot",
        content=response_text,
        message_type="text",
        wa_message_id=bot_wa_id,
    )
    db.add(bot_msg)

    await db.commit()

    logger.info(
        "Response sent",
        extra={
            "to": sender_phone,
            "response": response_text[:100],
            "wa_message_id": bot_wa_id,
        },
    )


def _generate_echo_response(text: str, contact_name: str | None) -> str:
    """
    Week 2: Echo bot with a little personality.
    This will be replaced by the AI Engine in Week 3.
    """
    name = contact_name or "amigo"

    # Handle common greetings
    text_lower = text.lower().strip()

    if text_lower in ("hola", "hi", "hello", "buenas", "buenos días", "buenas tardes"):
        return (
            f"¡Hola {name}! 👋 Soy el asistente virtual. "
            f"Estoy en modo de pruebas, pero pronto podré ayudarte con "
            f"información, agendar citas y mucho más. ¿En qué te puedo ayudar?"
        )

    if "precio" in text_lower or "costo" in text_lower or "cuánto" in text_lower:
        return (
            "📋 Pronto podré darte información de precios. "
            "Estoy en modo de pruebas por ahora. ¡Vuelve pronto!"
        )

    if "agendar" in text_lower or "cita" in text_lower or "hora" in text_lower:
        return (
            "📅 El sistema de agendamiento está en desarrollo. "
            "Pronto podrás agendar directamente por aquí."
        )

    # Default echo
    return (
        f"📨 Recibí tu mensaje: \"{text[:200]}\"\n\n"
        f"Soy un bot en modo de pruebas. "
        f"Pronto tendré inteligencia artificial para responderte de verdad 🤖"
    )


# ============================================
# DB Helpers
# ============================================
async def _get_or_create_contact(
    db: AsyncSession,
    phone: str,
    tenant_id,
) -> Contact:
    """Find existing contact by phone or create a new one."""
    from sqlalchemy import select

    result = await db.execute(
        select(Contact)
        .where(Contact.phone == phone)
        .where(Contact.tenant_id == tenant_id)
    )
    contact = result.scalar_one_or_none()

    if contact is None:
        contact = Contact(
            id=uuid4(),
            tenant_id=tenant_id,
            phone=phone,
            lead_status="new",
            source="whatsapp",
        )
        db.add(contact)
        await db.flush()  # Get the ID without committing

        logger.info(f"New contact created: {phone} (tenant={tenant_id})")

    return contact


async def _get_or_create_conversation(
    db: AsyncSession,
    contact_id,
    tenant_id,
) -> Conversation:
    """Find active conversation or create a new one."""
    from sqlalchemy import select

    result = await db.execute(
        select(Conversation)
        .where(Conversation.contact_id == contact_id)
        .where(Conversation.tenant_id == tenant_id)
        .where(Conversation.status == "active")
    )
    conversation = result.scalar_one_or_none()

    if conversation is None:
        conversation = Conversation(
            id=uuid4(),
            tenant_id=tenant_id,
            contact_id=contact_id,
            status="active",
            channel="whatsapp",
            source="organic",
        )
        db.add(conversation)
        await db.flush()

        logger.info(f"New conversation for contact={contact_id} (tenant={tenant_id})")

    return conversation


# ============================================
# Webhook Signature Verification (optional)
# ============================================
def _verify_signature(request: Request, body: dict):
    """
    Verify that the webhook request comes from Meta.
    Uses HMAC-SHA256 with your app secret.
    """
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature:
        logger.warning("No signature in webhook request")
        return

    import json
    body_bytes = json.dumps(body).encode("utf-8")
    expected = hmac.new(
        settings.WHATSAPP_APP_SECRET.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(f"sha256={expected}", signature):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")