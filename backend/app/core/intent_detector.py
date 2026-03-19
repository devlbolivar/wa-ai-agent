# app/core/intent_detector.py
"""
Intent Detection via OpenAI Function Calling.

Intents:
- BOOK_APPOINTMENT: paciente quiere agendar cita
- CANCEL_APPOINTMENT: paciente quiere cancelar
- CHECK_AVAILABILITY: paciente pregunta por disponibilidad
- GENERAL_QUERY: consulta general (RAG)
- GREETING: saludo
- HUMAN_ESCALATION: pide hablar con humano

El AI Engine llama a detect_intent() ANTES de generar la respuesta.
Si la intención es booking-related, el engine cambia al flujo de booking.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


# Function definitions for OpenAI
INTENT_FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "detect_intent",
            "description": "Detecta la intención del paciente en su mensaje",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": [
                            "BOOK_APPOINTMENT",
                            "CANCEL_APPOINTMENT",
                            "CHECK_AVAILABILITY",
                            "GENERAL_QUERY",
                            "GREETING",
                            "HUMAN_ESCALATION",
                        ],
                        "description": "La intención principal del mensaje",
                    },
                    "service": {
                        "type": "string",
                        "description": (
                            "Servicio mencionado si aplica "
                            "(ej: 'blanqueamiento', 'limpieza dental', 'corte de pelo')"
                        ),
                    },
                    "preferred_date": {
                        "type": "string",
                        "description": (
                            "Fecha preferida si se menciona "
                            "(ej: 'mañana', 'el lunes', 'esta semana', '15 de marzo')"
                        ),
                    },
                    "preferred_time": {
                        "type": "string",
                        "description": (
                            "Hora preferida si se menciona "
                            "(ej: 'en la mañana', 'a las 3', 'después de las 5')"
                        ),
                    },
                },
                "required": ["intent"],
            },
        },
    }
]


@dataclass
class DetectedIntent:
    intent: str
    service: Optional[str] = None
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None
    confidence: float = 0.0


async def detect_intent(
    message: str,
    conversation_context: list[dict] | None = None,
) -> DetectedIntent:
    """
    Detect user intent from their message using GPT-4o-mini function calling.

    Args:
        message: The user's latest message
        conversation_context: Recent messages for context (optional)

    Returns:
        DetectedIntent with intent type and extracted entities
    """
    messages = [
        {
            "role": "system",
            "content": (
                "Eres un detector de intenciones para un bot de WhatsApp de una "
                "clínica dental / salón de belleza en Chile. "
                "Analiza el mensaje del paciente y detecta su intención. "
                "Considera el contexto de la conversación si está disponible. "
                "Los pacientes hablan en español chileno informal."
            ),
        },
    ]

    # Add conversation context if available (last 4 messages)
    if conversation_context:
        for msg in conversation_context[-4:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

    messages.append({"role": "user", "content": message})

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=INTENT_FUNCTIONS,
            tool_choice={"type": "function", "function": {"name": "detect_intent"}},
            temperature=0.1,  # Baja temperatura para consistencia
            max_tokens=150,
        )

        tool_call = response.choices[0].message.tool_calls[0]
        args = json.loads(tool_call.function.arguments)

        return DetectedIntent(
            intent=args["intent"],
            service=args.get("service"),
            preferred_date=args.get("preferred_date"),
            preferred_time=args.get("preferred_time"),
            confidence=0.9,  # Function calling es bastante confiable
        )

    except Exception as e:
        logger.error(f"Intent detection failed: {e}")
        return DetectedIntent(intent="GENERAL_QUERY", confidence=0.3)