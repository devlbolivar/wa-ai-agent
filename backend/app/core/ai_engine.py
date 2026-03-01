"""
AI Engine — OpenAI version.
Uses GPT-4o-mini for responses + text-embedding-3-small for RAG.
Single API key for everything.
tenant_id is always a valid UUID — guaranteed by middleware.
"""

import logging
from uuid import UUID
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rag_pipeline import rag_pipeline
from app.models.message import Message

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class AIResponse:
    """Structured response from the AI Engine."""
    text: str
    confidence: float
    tokens_used: int
    sources_used: int
    intent: str | None = None


# ============================================
# Context Building (Sliding Window)
# ============================================
CONTEXT_WINDOW = 12

async def _build_context(
    db: AsyncSession,
    conversation_id: UUID,
) -> list[dict]:
    """
    Build conversation context with sliding window.
    ≤12 messages → send all. >12 → summarize old + keep last 8.
    """
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()

    if not messages:
        return []

    def to_openai_role(role: str) -> str:
        return "assistant" if role in ("bot", "human") else "user"

    # If within window, return all
    if len(messages) <= CONTEXT_WINDOW:
        return [
            {"role": to_openai_role(m.role), "content": m.content}
            for m in messages
        ]

    # Split: old → summary, recent → full
    old_messages = messages[:-8]
    recent_messages = messages[-8:]

    old_text = "\n".join(
        f"{'Paciente' if m.role == 'user' else 'Asistente'}: {m.content[:150]}"
        for m in old_messages[-10:]
    )

    summary = (
        f"[Resumen de la conversación anterior: El paciente y el asistente "
        f"han intercambiado {len(old_messages)} mensajes. "
        f"Últimos temas discutidos:\n{old_text}]"
    )

    context = [{"role": "user", "content": summary}]
    context.append({"role": "assistant", "content": "Entendido, continúo con el contexto anterior."})

    for m in recent_messages:
        context.append({
            "role": to_openai_role(m.role),
            "content": m.content,
        })

    return context


# ============================================
# System Prompt Builder
# ============================================
def _build_system_prompt(
    tenant_name: str | None,
    contact_name: str | None,
    rag_context: str,
) -> str:
    name = tenant_name or "nuestro negocio"
    patient = contact_name or "el paciente"

    return f"""Eres el asistente virtual de {name}. Tu trabajo es ayudar a los pacientes y clientes con información, agendar citas, y resolver dudas.

REGLAS IMPORTANTES:
- Responde SIEMPRE en español chileno amigable y profesional
- Sé conciso: máximo 2-3 oraciones por respuesta en WhatsApp
- Si no sabes algo con certeza, dilo honestamente
- Nunca inventes precios, horarios o servicios que no estén en tu base de conocimiento
- Si el paciente necesita algo que no puedes resolver, ofrécete a conectarlo con el equipo
- Usa emojis con moderación (1-2 por mensaje máximo)
- No uses markdown, asteriscos ni formato especial (es WhatsApp, no un documento)
- Si el paciente pregunta por algo y la información está en tu base de conocimiento, úsala

INFORMACIÓN DEL NEGOCIO:
{rag_context if rag_context else "No hay información cargada aún. Responde de forma general y sugiere contactar directamente al negocio para detalles específicos."}

El paciente se llama: {patient}

Responde de forma natural como si fueras un asistente humano escribiendo por WhatsApp."""


# ============================================
# LLM Call (OpenAI GPT-4o-mini)
# ============================================
async def _call_llm(
    system_prompt: str,
    conversation_context: list[dict],
    max_tokens: int = 400,
) -> tuple[str, int]:
    """
    Call GPT-4o-mini via OpenAI API.
    Returns: (response_text, total_tokens_used)
    """
    messages = [
        {"role": "system", "content": system_prompt},
        *conversation_context,
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "max_tokens": max_tokens,
                "temperature": 0.7,
                "messages": messages,
            },
        )
        response.raise_for_status()
        data = response.json()

    text = data["choices"][0]["message"]["content"]

    usage = data.get("usage", {})
    tokens = usage.get("total_tokens", 0)

    return text, tokens


# ============================================
# Main Engine Class
# ============================================
class AIEngine:
    """Orchestrates: context → RAG → LLM → response"""

    async def generate_response(
        self,
        tenant_id: UUID | None,
        conversation_id: UUID,
        contact_name: str | None,
        user_message: str,
        db: AsyncSession,
    ) -> AIResponse:
        """
        Generate an AI response. tenant_id is always valid.
        """
        try:
            # 1. RAG: Retrieve relevant knowledge
            rag_chunks = await rag_pipeline.retrieve(
                tenant_id=tenant_id,
                query=user_message,
                top_k=4,
            )
            rag_context = ""

            if rag_chunks:
                rag_context = "\n\n".join(
                    f"[{chunk.category.upper()}] {chunk.title}:\n{chunk.content}"
                    for chunk in rag_chunks
                )

            # 2. Build conversation context (sliding window)
            context = await _build_context(db, conversation_id)

            if not context or context[-1].get("content") != user_message:
                context.append({"role": "user", "content": user_message})

            # 3. Get tenant name
            from app.models.tenant import Tenant

            result = await db.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = result.scalar_one_or_none()
            tenant_name = tenant.name

            # 4. Build system prompt
            system_prompt = _build_system_prompt(
                tenant_name=tenant_name,
                contact_name=contact_name,
                rag_context=rag_context,
            )

            # 5. Dynamic max_tokens based on conversation length
            msg_count = len(context)
            if msg_count <= 15:
                max_tokens = 400
            elif msg_count <= 25:
                max_tokens = 200
            else:
                max_tokens = 120

            # 6. Call LLM
            response_text, tokens_used = await _call_llm(
                system_prompt=system_prompt,
                conversation_context=context,
                max_tokens=max_tokens,
            )

            # 7. Confidence based on RAG relevance
            confidence = 0.5
            if rag_chunks:
                top_score = rag_chunks[0].score
                if top_score > 0.8:
                    confidence = 0.95
                elif top_score > 0.6:
                    confidence = 0.8
                elif top_score > 0.4:
                    confidence = 0.65

            logger.info(
                f"AI response: {tokens_used} tokens, "
                f"confidence={confidence:.2f}, "
                f"rag_chunks={len(rag_chunks)}, "
                f"context_msgs={msg_count}"
            )

            return AIResponse(
                text=response_text,
                confidence=confidence,
                tokens_used=tokens_used,
                sources_used=len(rag_chunks),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            return self._fallback_response()

        except Exception as e:
            logger.exception(f"AI Engine error: {e}")
            return self._fallback_response()

    def _fallback_response(self) -> AIResponse:
        return AIResponse(
            text=(
                "Disculpa, estoy teniendo un problema técnico en este momento 😅 "
                "¿Podrías intentar de nuevo en unos minutos? "
                "Si es urgente, puedo conectarte con nuestro equipo directamente."
            ),
            confidence=0.0,
            tokens_used=0,
            sources_used=0,
        )


# Singleton
ai_engine = AIEngine()