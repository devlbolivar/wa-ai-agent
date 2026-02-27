import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.logger import setup_logging
from app.api.v1 import health

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup structured logging before startup
    setup_logging(level=logging.DEBUG if settings.DEBUG else logging.INFO)
    logger.info(f"Starting {settings.PROJECT_NAME} in {settings.ENVIRONMENT} mode")
    yield
    logger.info("Shutting down application")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    """
    Root endpoint redirecting to health check or providing a basic welcome.
    """
    return {"message": f"Welcome to {settings.PROJECT_NAME} API. Please see /docs for documentation."}
