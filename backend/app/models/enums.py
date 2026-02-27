import enum

class PaymentProviderEnum(str, enum.Enum):
    stripe = "stripe"
    mp = "mp"

class PlanEnum(str, enum.Enum):
    starter = "starter"
    pro = "pro"
    biz = "biz"

class ConversationStatusEnum(str, enum.Enum):
    active = "active"
    escalated = "escalated"
    closed = "closed"

class ChannelEnum(str, enum.Enum):
    whatsapp = "whatsapp"
    web = "web"

class RoleEnum(str, enum.Enum):
    user = "user"
    bot = "bot"
    human = "human"

class MessageTypeEnum(str, enum.Enum):
    text = "text"
    image = "image"
    audio = "audio"

class LeadStatusEnum(str, enum.Enum):
    new = "new"
    warm = "warm"
    hot = "hot"
    converted = "converted"
    cold = "cold"

class BookingStatusEnum(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"

class PaymentStatusEnum(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    refunded = "refunded"
    failed = "failed"

class KnowledgeCategoryEnum(str, enum.Enum):
    faq = "faq"
    service = "service"
    policy = "policy"
    promo = "promo"

class UserRoleEnum(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    agent = "agent"
