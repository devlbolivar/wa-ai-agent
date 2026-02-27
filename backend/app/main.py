import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.logger import setup_logging
from app.api.v1 import health, webhooks
from app.middleware import TenantMiddleware

settings = get_settings()

logger = logging.getLogger(__name__)

# ============================================
# Lifespan (startup / shutdown)
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup structured logging before startup
    setup_logging(level=logging.DEBUG if settings.DEBUG else logging.INFO)
    logger.info(f"🚀 Starting WA AI Agent [{settings.app_env}]")
    logger.info(f"📱 WhatsApp Phone ID: {settings.WHATSAPP_PHONE_NUMBER_ID or 'NOT SET'}")
    yield
    logger.info("👋 Shutting down WA AI Agent")

# ============================================
# App Instance
# ============================================
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# ============================================
# Middleware (order matters: last added = first executed)
# ============================================
# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TenantMiddleware)

# Include routers
app.include_router(health.router, prefix=settings.API_V1_STR)
app.include_router(webhooks.router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    """
    Root endpoint redirecting to health check or providing a basic welcome.
    """
    return {"message": f"Welcome to {settings.PROJECT_NAME} API. Please see /docs for documentation."}

# Triggering reload for new env vars
