# Process incoming messages
"""
Message Processing Tasks.
Handles debounce (grouping rapid messages) and async AI processing.

Flow:
1. Webhook receives message → pushes to Redis debounce buffer
2. Schedules this task with a 4-second delay (ETA)
3. Task fires → collects all buffered messages → processes as one
4. AI Engine generates response → sends via WhatsApp
"""

import asyncio
import json
import logging
from uuid import uuid4

import redis
from app.workers.celery_app import celery_app

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Sync Redis client for Celery (Celery tasks are sync by default)
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

DEBOUNCE_WINDOW = 4  # seconds


# ============================================
# Debounce: Buffer messages in Redis
# ============================================
def buffer_message(tenant_id: str, contact_phone: str, message_data: dict):
    """
    Called from the webhook handler.
    Pushes the message into a Redis list and schedules processing.

    Args:
        tenant_id: UUID string of the tenant
        contact_phone: Sender's phone number
        message_data: Dict with keys: text, msg_type, wa_message_id, timestamp
    """
    buffer_key = f"debounce:{tenant_id}:{contact_phone}"
    lock_key = f"debounce_lock:{tenant_id}:{contact_phone}"

    # Push message to buffer
    redis_client.rpush(buffer_key, json.dumps(message_data))
    redis_client.expire(buffer_key, DEBOUNCE_WINDOW + 10)  # TTL safety margin

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
@celery_app.task(
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
            f"Processing {len(messages)} buffered message(s) from {contact_phone}"
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
    1. Get/create contact and conversation in DB
    2. Save incoming message(s)
    3. Build context (sliding window)
    4. Call AI Engine (RAG + LLM)
    5. Send response via WhatsApp
    6. Save bot response to DB
    """
    from uuid import UUID
    from sqlalchemy import select

    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import NullPool
    from app.config import get_settings
    from app.models.contact import Contact
    from app.models.conversation import Conversation
    from app.models.message import Message
    from app.models.tenant import Tenant
    from app.core.ai_engine import AIEngine
    from app.core.whatsapp_client import WhatsAppClient

    ai_engine = AIEngine()
    whatsapp_client = WhatsAppClient()

    tenant_uuid = UUID(tenant_id) if tenant_id else None

    # Create a local engine and session maker for this Celery task execution
    # to avoid sharing the global engine across different asyncio event loops
    local_settings = get_settings()
    engine = create_async_engine(
        local_settings.database_url,
        poolclass=NullPool,
    )
    local_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with local_session() as db:
            wa_phone_number_id = None

        if tenant_uuid:
            tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
            tenant = tenant_result.scalar_one_or_none()
            if tenant:
                wa_phone_number_id = tenant.wa_phone_number_id

        # 1. Get or create contact
        query = select(Contact).where(Contact.phone == contact_phone)
        if tenant_uuid:
            query = query.where(Contact.tenant_id == tenant_uuid)
        result = await db.execute(query)
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

        # 2. Get or create active conversation
        query = select(Conversation).where(
            Conversation.contact_id == contact.id,
            Conversation.status == "active",
        )
        if tenant_uuid:
            query = query.where(Conversation.tenant_id == tenant_uuid)
        result = await db.execute(query)
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
            await whatsapp_client.mark_as_read(
                last_wa_message_id,
                phone_number_id=wa_phone_number_id,
            )

        # 5. Call AI Engine
        ai_response = await ai_engine.generate_response(
            tenant_id=tenant_uuid,
            conversation_id=conversation.id,
            contact_name=contact.name,
            user_message=combined_text,
            db=db,
        )

        # 6. Send response via WhatsApp
        wa_result = await whatsapp_client.send_text_message(
            to=contact_phone,
            body=ai_response.text,
            phone_number_id=wa_phone_number_id,
        )
        bot_wa_id = wa_result.get("messages", [{}])[0].get("id", "")

        # 7. Save bot response to DB
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
    finally:
        # Prevent connection leaks
        await engine.dispose()