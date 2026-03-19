# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands are run from the `backend/` directory unless noted.

**Infrastructure (from repo root):**
```bash
docker-compose up -d        # Start PostgreSQL (5432), Redis (6379), Qdrant (6333)
docker-compose down
```

**Server:**
```bash
uvicorn backend.app.main:app --reload          # From repo root
# or from backend/:
uvicorn app.main:app --reload
```

**Celery worker (from backend/ with venv active):**
```bash
celery -A app.workers.celery_app worker -Q messages --loglevel=info
```

**Database migrations (from backend/):**
```bash
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic downgrade -1
```

**Tests (from backend/):**
```bash
pytest                          # All tests
pytest tests/api/test_health.py # Single file
pytest -k "test_name"           # Single test by name
pytest --cov=app                # With coverage
```

**Seed scripts (from repo root):**
```bash
python backend/scripts/seed_tenant.py    # Create dev tenant
python backend/scripts/seed_dental.py   # Load dental KB + vectorize in Qdrant
```

## Architecture

### Overview
Multi-tenant SaaS where each business (tenant) connects their WhatsApp number and gets an AI assistant. A single server instance handles all tenants. Each tenant is identified by their `wa_phone_number_id` from Meta.

### Middleware Chain (execution order, innermost first)
`BodyCacheMiddleware` → `TenantMiddleware` → `CORSMiddleware`

Middlewares are added in **reverse** order in FastAPI — last-added executes first. `BodyCacheMiddleware` caches the request body so it can be read multiple times (both `TenantMiddleware` and the route handler need to read it). `TenantMiddleware` resolves `tenant_id` from the webhook payload's `phone_number_id` (or from `X-Tenant-ID` header for dashboard/dev routes) and injects it into `request.state`.

**Important:** Webhook POST returns 200 to Meta even for unknown tenants (Meta retries on non-200). Use `get_tenant_id(request)` or `get_tenant(request)` from `app/middleware/tenant.py` in route handlers.

### Message Processing Flow
1. **Webhook** (`POST /api/v1/webhook/whatsapp`) → returns 200 immediately
2. **Debounce buffer** — `buffer_message()` pushes to Redis list (`debounce:{tenant_id}:{phone}`) and schedules a Celery task with 4-second countdown
3. **Celery task** (`process_buffered_messages`) — collects all buffered messages, combines text, calls `_async_process_message()` via `asyncio.run()`
4. **Async pipeline** — find/create Contact → find/create Conversation → save incoming Message → mark as read → AI Engine → send WhatsApp reply → save bot Message

### AI Engine (`app/core/ai_engine.py`)
Orchestrates: sliding window context (≤12 msgs: full; >12: summarize old + last 8) → RAG retrieval → system prompt assembly → GPT-4o-mini call → confidence scoring → fallback on any failure.

### RAG Pipeline (`app/core/rag_pipeline.py`)
Each tenant has its own Qdrant collection (`tenant_{uuid_with_underscores}`). Embeddings use `text-embedding-3-small` (1536 dims). Knowledge base entries are stored in both PostgreSQL (source of truth) and Qdrant (search index). Use `query_points()` — not the deprecated `search()`.

### Database Sessions
- **FastAPI routes:** use `app/core/database.py`'s `async_session` (connection pool)
- **Celery tasks:** use `app/workers/db.py`'s `worker_session` (NullPool — required because `asyncio.run()` creates/destroys event loops, which breaks pooled connections)

### Multi-tenancy Pattern
`tenant_id` (UUID) is on every table. This is intentional denormalization — avoids multi-table JOINs on every query. All queries must filter by `tenant_id`.

### Models (`app/models/__init__.py`)
All models must be imported in `__init__.py` for Alembic to auto-detect schema changes. Current models: `Tenant`, `Contact`, `Conversation`, `Message`, `Booking`, `Payment`, `KnowledgeBase`, `User`, `TenantCalendarConfig`.

### Configuration
`app/config.py` uses `pydantic-settings` with `@lru_cache`. `.env` file lives at `backend/.env`. Settings are accessed via `get_settings()` singleton. Key variables: `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `QDRANT_HOST`.

### Enums
Shared enums (roles, status values, categories, etc.) are centralized in `app/models/enums.py`.
