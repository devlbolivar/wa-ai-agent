"""
Seed script — Load dental clinic FAQ into Knowledge Base + Qdrant.
Creates realistic data for "Sonrisa Plus Dental" test tenant.

Usage:
    python -m scripts.seed_dental_kb
"""

import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.config import get_settings
from app.core.database import async_session
from app.models.tenant import Tenant
from app.models.knowledge_base import KnowledgeBase
from app.core.rag_pipeline import rag_pipeline

settings = get_settings()


# ============================================
# Dental Clinic Knowledge Base
# ============================================
DENTAL_KB = [
    # ----- SERVICIOS -----
    {
        "title": "Limpieza dental",
        "content": (
            "La limpieza dental o profilaxis tiene un valor de $35.000 CLP. "
            "Dura aproximadamente 30 a 40 minutos. Incluye eliminación de sarro, "
            "pulido dental y aplicación de flúor. Se recomienda hacerla cada 6 meses. "
            "No requiere anestesia y el paciente puede comer normalmente después."
        ),
        "category": "servicios",
    },
    {
        "title": "Blanqueamiento dental",
        "content": (
            "Ofrecemos blanqueamiento dental LED en clínica por $120.000 CLP. "
            "La sesión dura 1 hora aproximadamente. Los resultados son inmediatos, "
            "aclarando entre 3 a 6 tonos. Incluye kit de mantenimiento para la casa. "
            "Se recomienda no consumir café, vino tinto ni alimentos con colorantes "
            "por 48 horas después del procedimiento."
        ),
        "category": "servicios",
    },
    {
        "title": "Ortodoncia brackets",
        "content": (
            "El tratamiento de ortodoncia con brackets metálicos tiene un valor total "
            "desde $1.200.000 CLP, que se puede pagar en cuotas mensuales de $50.000 CLP. "
            "Incluye la instalación, controles mensuales y retiro. "
            "La duración promedio del tratamiento es de 18 a 24 meses. "
            "También ofrecemos brackets estéticos (cerámicos) desde $1.500.000 CLP."
        ),
        "category": "servicios",
    },
    {
        "title": "Implante dental",
        "content": (
            "El implante dental tiene un valor de $650.000 CLP por pieza, "
            "que incluye el implante de titanio, la cirugía y la corona definitiva. "
            "El proceso completo toma entre 3 a 6 meses (tiempo de osteointegración). "
            "Requiere evaluación previa con radiografía panorámica. "
            "Financiamiento disponible hasta en 12 cuotas sin interés."
        ),
        "category": "servicios",
    },
    {
        "title": "Extracción de muelas del juicio",
        "content": (
            "La extracción simple de muelas del juicio tiene un valor de $45.000 CLP por pieza. "
            "Extracciones complejas (muela impactada) desde $80.000 CLP. "
            "Se realiza con anestesia local. El procedimiento dura entre 20 y 45 minutos. "
            "Incluye receta de medicamentos y control post-operatorio gratuito a los 7 días."
        ),
        "category": "servicios",
    },
    {
        "title": "Resina dental (tapaduras)",
        "content": (
            "Las resinas o tapaduras dentales van desde $25.000 a $55.000 CLP "
            "dependiendo del tamaño y ubicación. Son del color del diente, "
            "estéticas y duraderas. El procedimiento dura entre 20 y 40 minutos "
            "con anestesia local. El paciente puede comer después de 2 horas."
        ),
        "category": "servicios",
    },
    {
        "title": "Endodoncia (tratamiento de conducto)",
        "content": (
            "La endodoncia tiene un valor desde $85.000 CLP para piezas anteriores "
            "y desde $120.000 CLP para molares. El tratamiento salva la pieza dental "
            "cuando la caries ha llegado al nervio. Puede requerir 1 o 2 sesiones "
            "de aproximadamente 1 hora cada una. Después se necesita una corona o resina."
        ),
        "category": "servicios",
    },

    # ----- HORARIOS -----
    {
        "title": "Horarios de atención",
        "content": (
            "Atendemos de lunes a viernes de 9:00 a 19:00 horas, "
            "y sábados de 9:00 a 14:00 horas. "
            "Los domingos y festivos no atendemos. "
            "La última hora disponible para agendar es 1 hora antes del cierre. "
            "Contamos con horarios extendidos los martes y jueves hasta las 20:00."
        ),
        "category": "horarios",
    },

    # ----- EQUIPO -----
    {
        "title": "Equipo profesional",
        "content": (
            "Nuestro equipo está formado por: "
            "Dra. Carolina Méndez — Odontóloga general, especialista en estética dental. "
            "Dr. Sebastián Rojas — Cirujano maxilofacial, especialista en implantes. "
            "Dra. Valentina Torres — Ortodoncista, especialista en brackets y alineadores. "
            "Todos nuestros profesionales están registrados en la Superintendencia de Salud."
        ),
        "category": "equipo",
    },

    # ----- UBICACIÓN -----
    {
        "title": "Ubicación y cómo llegar",
        "content": (
            "Estamos ubicados en Av. Providencia 1234, oficina 502, Providencia, Santiago. "
            "Referencia: a 2 cuadras de la estación de metro Pedro de Valdivia. "
            "El edificio tiene estacionamiento subterráneo disponible para pacientes "
            "con tarifa preferencial de $1.000 CLP/hora."
        ),
        "category": "ubicacion",
    },

    # ----- POLÍTICAS -----
    {
        "title": "Política de cancelación y reagendamiento",
        "content": (
            "Las citas se pueden cancelar o reagendar hasta 24 horas antes "
            "sin costo. Cancelaciones con menos de 24 horas de anticipación "
            "o inasistencias sin aviso tendrán un cargo de $10.000 CLP "
            "que se descuenta del abono de la próxima cita. "
            "Para reagendar, puedes escribirnos por WhatsApp o llamar al teléfono de la clínica."
        ),
        "category": "politicas",
    },
    {
        "title": "Formas de pago",
        "content": (
            "Aceptamos efectivo, tarjeta de débito, tarjeta de crédito "
            "(hasta 12 cuotas sin interés en tratamientos sobre $200.000), "
            "y transferencia bancaria. "
            "Para agendar una cita se requiere un abono de $15.000 CLP "
            "que se descuenta del valor total del tratamiento. "
            "El abono se puede pagar por transferencia o tarjeta a través del link de pago "
            "que te enviamos por WhatsApp."
        ),
        "category": "politicas",
    },
    {
        "title": "Convenios y seguros",
        "content": (
            "Tenemos convenio con Fonasa (nivel 2 y 3) para prestaciones básicas "
            "como limpieza, extracciones y resinas. "
            "También trabajamos con Colmena, Cruz Blanca y Banmédica. "
            "Consulta por tu isapre específica y te confirmamos la cobertura."
        ),
        "category": "politicas",
    },

    # ----- FAQ -----
    {
        "title": "¿Duele la limpieza dental?",
        "content": (
            "La limpieza dental generalmente no duele. Puedes sentir algo de "
            "presión o sensibilidad si hay acumulación de sarro, pero no es doloroso. "
            "Si tienes mucha sensibilidad, podemos aplicar anestesia tópica "
            "(gel en las encías) sin costo adicional."
        ),
        "category": "faq",
    },
    {
        "title": "¿Cuánto dura el blanqueamiento?",
        "content": (
            "Los resultados del blanqueamiento dental duran entre 6 meses y 2 años, "
            "dependiendo de los hábitos del paciente. Factores como consumo de café, "
            "té, vino tinto y tabaco reducen la duración. "
            "El kit de mantenimiento que entregamos ayuda a prolongar los resultados."
        ),
        "category": "faq",
    },
    {
        "title": "¿Atienden urgencias?",
        "content": (
            "Sí, atendemos urgencias dentales de lunes a viernes. "
            "Si tienes dolor agudo, fractura dental, o una emergencia, "
            "escríbenos por WhatsApp con la palabra URGENCIA y te daremos "
            "un horario lo antes posible, normalmente el mismo día. "
            "El valor de la consulta de urgencia es $30.000 CLP."
        ),
        "category": "faq",
    },
    {
        "title": "¿Atienden niños?",
        "content": (
            "Sí, atendemos niños desde los 3 años. "
            "Realizamos controles preventivos, aplicación de sellantes, "
            "fluorizaciones y tratamientos básicos. "
            "La primera consulta infantil tiene un valor de $20.000 CLP "
            "e incluye revisión completa y plan de tratamiento."
        ),
        "category": "faq",
    },
]


async def seed():
    async with async_session() as db:
        # Find the dev tenant
        result = await db.execute(
            select(Tenant).where(Tenant.slug == "dev")
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            print("❌ Dev tenant not found. Run seed_dev_tenant.py first.")
            return

        # Update tenant name to dental clinic
        tenant.name = "Sonrisa Plus Dental"
        await db.commit()

        print(f"📋 Loading KB for: {tenant.name}")
        print(f"   Tenant ID: {tenant.id}")
        print()

        # Clear existing KB entries for this tenant
        from sqlalchemy import delete
        await db.execute(
            delete(KnowledgeBase).where(KnowledgeBase.tenant_id == tenant.id)
        )
        await db.commit()

        # Insert KB entries
        entries_for_reindex = []

        for item in DENTAL_KB:
            kb_id = str(uuid4())
            entry = KnowledgeBase(
                id=kb_id,
                tenant_id=tenant.id,
                title=item["title"],
                content=item["content"],
                category=item["category"],
                is_active=True,
            )
            db.add(entry)

            entries_for_reindex.append({
                "kb_id": kb_id,
                "title": item["title"],
                "content": item["content"],
                "category": item["category"],
            })

            print(f"  ✅ [{item['category']:<12}] {item['title']}")

        await db.commit()

        # Vectorize all entries in Qdrant
        print()
        print("🔮 Vectorizing in Qdrant...")
        await rag_pipeline.reindex_tenant(
            tenant_id=tenant.id,
            entries=entries_for_reindex,
        )

        print()
        print(f"🎉 Done! {len(DENTAL_KB)} entries loaded and vectorized.")
        print()
        print("Test it by asking the bot:")
        print('  → "¿Cuánto sale un blanqueamiento?"')
        print('  → "¿Qué horarios tienen?"')
        print('  → "¿Atienden urgencias?"')
        print('  → "¿Cuánto cuesta una limpieza?"')


if __name__ == "__main__":
    asyncio.run(seed())