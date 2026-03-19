"""
Message Processing Tasks.
Handles debounce (grouping rapid messages) and async AI processing.

tenant_id is ALWAYS a valid UUID string — guaranteed by the middleware
and validated by buffer_message before enqueueing.

Uses worker_session (NullPool) instead of the FastAPI async_session
to avoid event loop conflicts between asyncio.run() calls.
"""

import asyncio
import json
import logging
from uuid import UUID, uuid4
import redis
from celery import shared_task
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

DEBOUNCE_WINDOW = 4  # seconds

# ============================================
# Debounce: Buffer messages in Redis
# ============================================
def buffer_message(tenant_id: str, contact_phone: str, message_data: dict):
    """
    Push message into Redis debounce buffer and schedule processing.
    tenant_id must be a valid UUID string — rejects empty values.
    """
    if not tenant_id:
        logger.error(
            f"Rejected message from {contact_phone}: no tenant_id. "
            f"This should never happen — check TenantMiddleware."
        )
        return

    buffer_key = f"debounce:{tenant_id}:{contact_phone}"
    lock_key = f"debounce_lock:{tenant_id}:{contact_phone}"

    # Push message to buffer
    redis_client.rpush(buffer_key, json.dumps(message_data))
    redis_client.expire(buffer_key, DEBOUNCE_WINDOW + 10)

    # Only schedule processing if not already scheduled
    if redis_client.set(lock_key, "1", nx=True, ex=DEBOUNCE_WINDOW + 2):
        # Schedule the processing task with a delay
        process_buffered_messages.apply_async(
            args=[tenant_id, contact_phone],
            countdown=DEBOUNCE_WINDOW,
        )
        logger.debug(f"Debounce scheduled for {contact_phone} in {DEBOUNCE_WINDOW}s")
    else:
        logger.debug(f"Debounce already scheduled for {contact_phone}, message buffered")


# ============================================
# Process: Collect buffered messages → AI → Reply
# ============================================
@shared_task(
    name="app.workers.message_tasks.process_buffered_messages",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def process_buffered_messages(self, tenant_id: str, contact_phone: str):
    """
    Collect all buffered messages for this contact and process them as one.

    If the patient sent 5 messages in 4 seconds:
        "Hola"
        "Quiero agendar"
        "Para el martes"
        "En la mañana"
        "Gracias"
    → They become ONE input: "Hola\nQuiero agendar\nPara el martes\nEn la mañana\nGracias"
    → ONE call to the AI Engine
    → ONE response to the patient
    """
    buffer_key = f"debounce:{tenant_id}:{contact_phone}"
    lock_key = f"debounce_lock:{tenant_id}:{contact_phone}"

    try:
        # Collect all buffered messages
        raw_messages = redis_client.lrange(buffer_key, 0, -1)
        redis_client.delete(buffer_key)
        redis_client.delete(lock_key)

        if not raw_messages:
            logger.warning(f"No buffered messages for {contact_phone}")
            return

        messages = [json.loads(m) for m in raw_messages]
        logger.info(
            f"Processing {len(messages)} buffered message(s) "
            f"from {contact_phone} (tenant={tenant_id})"
        )

        # Combine text from all buffered messages
        combined_text = "\n".join(
            m["text"] for m in messages if m.get("text")
        )

        # Get the last wa_message_id (for mark-as-read and reply context)
        last_wa_id = messages[-1].get("wa_message_id", "")

        # Run async processing in a new event loop
        # (Celery tasks are sync, but our DB/AI/WhatsApp calls are async)
        result = asyncio.run(
            _async_process_message(
                tenant_id=tenant_id,
                contact_phone=contact_phone,
                combined_text=combined_text,
                last_wa_message_id=last_wa_id,
                message_count=len(messages),
            )
        )

        logger.info(
            f"Processed message for {contact_phone}: "
            f"{len(messages)} msgs → 1 AI call → response sent"
        )
        return result

    except Exception as e:
        logger.exception(f"Error processing messages for {contact_phone}: {e}")
        # Retry on failure
        raise self.retry(exc=e)


async def _async_process_message(
    tenant_id: str,
    contact_phone: str,
    combined_text: str,
    last_wa_message_id: str,
    message_count: int,
) -> dict:
    """
    Async processing pipeline:
    tenant_id is always a valid UUID string.
    """


    from sqlalchemy import select

    from app.workers.db import worker_session
    from app.models.contact import Contact
    from app.models.conversation import Conversation
    from app.models.message import Message
    from app.core.ai_engine import ai_engine
    from app.core.whatsapp_client import whatsapp_client

    tenant_uuid = UUID(tenant_id)
    async with worker_session() as db:
        # 1. Get or create contact (always scoped to tenant)
        result = await db.execute(
            select(Contact).where(
                Contact.phone == contact_phone,
                Contact.tenant_id == tenant_uuid,
            )
        )
        contact = result.scalar_one_or_none()

        if contact is None:
            contact = Contact(
                id=uuid4(),
                tenant_id=tenant_uuid,
                phone=contact_phone,
                lead_status="new",
                source="whatsapp",
            )
            db.add(contact)
            await db.flush()
            logger.info(f"New contact: {contact_phone} (tenant={tenant_id})")

        # 2. Get or create active conversation (always scoped to tenant)
        result = await db.execute(
            select(Conversation).where(
                Conversation.contact_id == contact.id,
                Conversation.tenant_id == tenant_uuid,
                Conversation.status == "active",
            )
        )
        conversation = result.scalar_one_or_none()

        if conversation is None:
            conversation = Conversation(
                id=uuid4(),
                tenant_id=tenant_uuid,
                contact_id=contact.id,
                status="active",
                channel="whatsapp",
                source="organic",
            )
            db.add(conversation)
            await db.flush()

        # 3. Save incoming message
        incoming_msg = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            tenant_id=tenant_uuid,
            role="user",
            content=combined_text,
            message_type="text",
            wa_message_id=last_wa_message_id,
        )
        db.add(incoming_msg)
        await db.flush()

        # 4. Mark as read
        if last_wa_message_id:
            await whatsapp_client.mark_as_read(last_wa_message_id)

        # 5. AI Engine: RAG + LLM
        ai_response = await ai_engine.generate_response(
            tenant_id=tenant_uuid,
            conversation_id=conversation.id,
            contact_name=contact.name,
            user_message=combined_text,
            db=db,
            contact_id=contact.id,
        )

        # 6. Send response via WhatsApp
        wa_result = await whatsapp_client.send_text_message(
            to=contact_phone,
            body=ai_response.text,
        )
        bot_wa_id = wa_result.get("messages", [{}])[0].get("id", "")

        # 7. Save bot response
        bot_msg = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            tenant_id=tenant_uuid,
            role="bot",
            content=ai_response.text,
            message_type="text",
            wa_message_id=bot_wa_id,
            confidence=ai_response.confidence,
            tokens_used=ai_response.tokens_used,
        )
        db.add(bot_msg)
        await db.commit()

        return {
            "contact_phone": contact_phone,
            "response_length": len(ai_response.text),
            "tokens_used": ai_response.tokens_used,
            "confidence": ai_response.confidence,
        }
