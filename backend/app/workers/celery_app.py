# Celery config
"""
Celery Application Configuration.
Uses Redis as broker and result backend.

Run worker:
    celery -A app.workers.celery_app worker -Q messages --loglevel=info

Run beat (for scheduled tasks, Week 9):
    celery -A app.workers.celery_app beat --loglevel=info
"""

from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "wa_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Santiago",
    enable_utc=True,

    # Retry policy
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Concurrency
    worker_prefetch_multiplier=1,
    worker_concurrency=4,

    # Task routing
    task_routes={
        "app.workers.message_tasks.*": {"queue": "messages"},
    },

    # Result expiration (1 hour)
    result_expires=3600,

    # Auto-discover tasks in these modules
    imports=[
        "app.workers.message_tasks",
    ],
)