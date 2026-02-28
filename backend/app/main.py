"""
WhatsApp AI Agent — FastAPI Application (Week 3).
Added: Knowledge Base API router.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.workers.celery_app import celery_app  # Ensure Celery connects to Redis instead of default amqp
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.knowledge_base import router as kb_router
from app.middleware.body_cache import BodyCacheMiddleware
from app.middleware.tenant import TenantMiddleware

settings = get_settings()

logging.basicConfig(
    level=logging.INFO if not settings.app_debug else logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Starting WA AI Agent [{settings.app_env}]")
    logger.info(f"📱 WhatsApp Phone ID: {settings.WHATSAPP_PHONE_NUMBER_ID or 'NOT SET'}")
    logger.info(f"📐 OpenAI API: {'SET' if settings.openai_api_key else 'NOT SET'}")
    yield
    logger.info("👋 Shutting down WA AI Agent")


app = FastAPI(
    title="WhatsApp AI Agent",
    description="AI-powered WhatsApp sales & support agent for SMBs",
    version="0.3.0",
    lifespan=lifespan,
)

# Middleware (last added = first executed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantMiddleware)
app.add_middleware(BodyCacheMiddleware)

# Routes
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(kb_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "wa-ai-agent",
        "version": "0.3.0",
        "env": settings.app_env,
    }