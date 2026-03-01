"""
Knowledge Base API Endpoints.
CRUD for KB entries with automatic vectorization in Qdrant.

tenant_id is guaranteed by TenantMiddleware via X-Tenant-ID header.
Dashboard routes that lack the header get 401 from the middleware.
"""

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.tenant import get_tenant_id
from app.models.knowledge_base import KnowledgeBase
from app.core.rag_pipeline import rag_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


# ============================================
# Schemas
# ============================================
class KBCreateRequest(BaseModel):
    title: str
    content: str
    category: str = "general"  # servicios, precios, horarios, faq, politicas


class KBUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    category: str | None = None
    is_active: bool | None = None


class KBResponse(BaseModel):
    id: str
    title: str
    content: str
    category: str
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================
# Endpoints
# ============================================
@router.post("", response_model=KBResponse, status_code=201)
async def create_kb_entry(
    body: KBCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new KB entry and vectorize it automatically."""
    tenant_id = get_tenant_id(request)
    kb_id = str(uuid4())

    entry = KnowledgeBase(
        id=kb_id,
        tenant_id=tenant_id,
        title=body.title,
        content=body.content,
        category=body.category,
        is_active=True,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    # Vectorize in Qdrant
    await rag_pipeline.index_knowledge(
        tenant_id=tenant_id,
        kb_id=kb_id,
        title=body.title,
        content=body.content,
        category=body.category,
    )

    logger.info(f"KB entry created and indexed: {body.title} (tenant={tenant_id})")
    return entry


@router.get("", response_model=list[KBResponse])
async def list_kb_entries(
    request: Request,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all KB entries for the current tenant."""
    tenant_id = get_tenant_id(request)

    query = select(KnowledgeBase).where(
        KnowledgeBase.tenant_id == tenant_id,
        KnowledgeBase.is_active == True,
    )

    if category:
        query = query.where(KnowledgeBase.category == category)

    query = query.order_by(KnowledgeBase.category, KnowledgeBase.title)
    result = await db.execute(query)

    return result.scalars().all()


@router.get("/{kb_id}", response_model=KBResponse)
async def get_kb_entry(
    kb_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get a single KB entry."""
    tenant_id = get_tenant_id(request)

    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.tenant_id == tenant_id,
        )
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=404, detail="KB entry not found")

    return entry


@router.put("/{kb_id}", response_model=KBResponse)
async def update_kb_entry(
    kb_id: str,
    body: KBUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update a KB entry and re-vectorize if content changed."""
    tenant_id = get_tenant_id(request)

    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.tenant_id == tenant_id,
        )
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=404, detail="KB entry not found")

    # Track if content changed (needs re-vectorization)
    content_changed = False

    if body.title is not None:
        entry.title = body.title
        content_changed = True
    if body.content is not None:
        entry.content = body.content
        content_changed = True
    if body.category is not None:
        entry.category = body.category
        content_changed = True
    if body.is_active is not None:
        entry.is_active = body.is_active

    await db.commit()
    await db.refresh(entry)

    # Re-vectorize if content changed
    if content_changed and entry.is_active:
        await rag_pipeline.index_knowledge(
            tenant_id=tenant_id,
            kb_id=kb_id,
            title=entry.title,
            content=entry.content,
            category=entry.category,
        )
        logger.info(f"KB entry re-indexed: {entry.title}")
    elif not entry.is_active:
        # Remove from vector DB if deactivated
        await rag_pipeline.delete_knowledge(tenant_id, kb_id)
        logger.info(f"KB entry removed from index: {entry.title}")

    return entry


@router.delete("/{kb_id}", status_code=204)
async def delete_kb_entry(
    kb_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a KB entry from DB and vector store."""
    tenant_id = get_tenant_id(request)

    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.tenant_id == tenant_id,
        )
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=404, detail="KB entry not found")

    await db.delete(entry)
    await db.commit()

    # Remove from Qdrant
    await rag_pipeline.delete_knowledge(tenant_id, kb_id)

    logger.info(f"KB entry deleted: {entry.title}")