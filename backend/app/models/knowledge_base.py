import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP

from app.models.base import Base, UUIDMixin
from app.models.enums import KnowledgeCategoryEnum

class KnowledgeBase(Base, UUIDMixin):
    __tablename__ = "knowledge_base"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    title: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str | None] = mapped_column(Text)
    category: Mapped[KnowledgeCategoryEnum | None] = mapped_column(Enum(KnowledgeCategoryEnum))
    embedding_id: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="knowledge_bases")
