# Import all models here so Alembic can discover them
from app.models.base import Base
from app.models.tenant import Tenant
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.booking import Booking
from app.models.payment import Payment
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User

__all__ = [
    "Base",
    "Tenant",
    "Contact",
    "Conversation",
    "Message",
    "Booking",
    "Payment",
    "KnowledgeBase",
    "User",
]
