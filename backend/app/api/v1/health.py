from fastapi import APIRouter
from app.config import settings

router = APIRouter()

@router.get("/health", tags=["health"])
async def check_health():
    """
    Health check endpoint for the application.
    """
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }
