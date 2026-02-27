"""
Tenant Resolution Middleware.
Identifies which tenant (client/business) owns the incoming request.

Two resolution strategies:
1. Webhook requests → resolve by WhatsApp phone_number_id
2. Dashboard/API requests → resolve by JWT token (Week 7)

The resolved tenant_id is injected into request.state.tenant_id
and is available to all downstream route handlers.
"""

import logging
from uuid import UUID

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response, JSONResponse
from sqlalchemy import select

from app.core.database import async_session
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


# Routes that don't need tenant resolution
TENANT_EXEMPT_PATHS = {
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}

# Webhook paths — resolve tenant by phone_number_id
WEBHOOK_PATHS = {
    "/api/v1/webhook/whatsapp",
}


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Resolves tenant_id for every request and injects it into request.state.

    For webhook requests:
        - Extracts phone_number_id from the Meta payload
        - Looks up tenant in DB by wa_phone_number_id
        - GET verification requests (hub.mode=subscribe) are exempt

    For dashboard/API requests (Week 7+):
        - Extracts tenant_id from JWT claims
        - For now, falls back to default tenant in dev mode
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path

        # Skip exempt paths
        if path in TENANT_EXEMPT_PATHS or path.startswith("/docs"):
            return await call_next(request)

        # Skip all webhook paths (tenant is resolved in the route handler)
        if path in WEBHOOK_PATHS:
            return await call_next(request)

        # --- Dashboard/API: resolve by JWT (Week 7) ---
        # For now in development, use default tenant or header
        tenant = await self._resolve_from_header_or_default(request)
        request.state.tenant_id = tenant.id if tenant else None
        request.state.tenant = tenant

        return await call_next(request)

    async def _resolve_from_header_or_default(self, request: Request) -> Tenant | None:
        """
        For development: resolve tenant from X-Tenant-ID header
        or fall back to the first active tenant.

        In Week 7 this will be replaced with JWT-based resolution.
        """
        # Check for explicit tenant header (useful for testing)
        tenant_header = request.headers.get("X-Tenant-ID")

        async with async_session() as db:
            if tenant_header:
                try:
                    tenant_uuid = UUID(tenant_header)
                    result = await db.execute(
                        select(Tenant).where(
                            Tenant.id == tenant_uuid,
                        )
                    )
                    tenant = result.scalar_one_or_none()
                    if tenant:
                        return tenant
                except (ValueError, AttributeError):
                    logger.warning(f"Invalid X-Tenant-ID header: {tenant_header}")

            # Fallback: first active tenant (dev only)
            result = await db.execute(
                select(Tenant).limit(1)
            )
            return result.scalar_one_or_none()


# ============================================
# Helper: get tenant_id from request
# ============================================
def get_tenant_id(request: Request) -> UUID | None:
    """
    Utility to extract tenant_id from request state.
    Use in route handlers: tenant_id = get_tenant_id(request)
    """
    return getattr(request.state, "tenant_id", None)


def get_tenant(request: Request) -> Tenant | None:
    """
    Utility to extract full tenant object from request state.
    Use in route handlers: tenant = get_tenant(request)
    """
    return getattr(request.state, "tenant", None)


def require_tenant(request: Request) -> UUID:
    """
    Strict version — raises 400 if no tenant resolved.
    Use as FastAPI dependency:

        @router.get("/something")
        async def something(tenant_id: UUID = Depends(require_tenant)):
            ...
    """
    tenant_id = get_tenant_id(request)
    if tenant_id is None:
        raise HTTPException(
            status_code=400,
            detail="Could not resolve tenant for this request",
        )
    return tenant_id