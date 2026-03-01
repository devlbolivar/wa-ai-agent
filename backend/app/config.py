"""
Application configuration via pydantic-settings.
Week 3: OpenAI for both embeddings and chat completions.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # --- App ---
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # --- Database ---
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/app_db"
    database_url_sync: str = "postgresql://postgres:password@localhost:5432/app_db"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- WhatsApp Cloud API ---
    WHATSAPP_ACCESS_TOKEN: str = ""
    whatsapp_phone_number_id: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_API_VERSION: str = "v21.0"

    # --- Qdrant (Vector DB) ---
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # --- OpenAI (Embeddings + Chat) ---
    openai_api_key: str = ""

    @property
    def whatsapp_api_url(self) -> str:
        return f"https://graph.facebook.com/{self.WHATSAPP_API_VERSION}"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()