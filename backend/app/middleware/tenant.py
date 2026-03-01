"""
Tenant Resolution Middleware.
Identifies which tenant (client/business) owns the incoming request.

Resolution strategies:
1. Webhook POST  → resolve by WhatsApp phone_number_id from payload
2. Webhook GET   → exempt (Meta verification challenge, no tenant needed)
3. Dashboard/API → resolve by X-Tenant-ID header (dev) / JWT (Week 7)
4. Exempt paths  → skip (/health, /docs)

RULE: tenant_id is NEVER null for business routes.
If tenant cannot be resolved, the request is rejected or ignored.
"""

import logging
from uuid import UUID

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
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

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path

        # --- Exempt paths: no tenant needed ---
        if path in TENANT_EXEMPT_PATHS or path.startswith("/docs"):
            return await call_next(request)

        # --- Webhook GET: Meta verification challenge, no tenant needed ---
        if path in WEBHOOK_PATHS and request.method == "GET":
            return await call_next(request)

        # --- Webhook POST: resolve by phone_number_id ---
        if path in WEBHOOK_PATHS and request.method == "POST":
            tenant = await self._resolve_from_webhook(request)

            if tenant is None:
                # Return 200 to Meta (never return errors to Meta, they retry)
                # but do NOT process the message — no tenant = no processing
                logger.error(
                    "Webhook received for unknown phone_number_id. "
                    "Message will NOT be processed. "
                    "Verify the phone_number_id matches a tenant in the DB."
                )
                return Response(
                    content='{"status":"ignored","reason":"unknown_tenant"}',
                    status_code=200,
                    media_type="application/json",
                )

            request.state.tenant_id = tenant.id
            request.state.tenant = tenant
            return await call_next(request)

        # --- Dashboard/API routes: resolve by header (dev) or JWT (Week 7) ---
        tenant = await self._resolve_from_header(request)

        if tenant is None:
            raise HTTPException(
                status_code=401,
                detail="Could not resolve tenant. Provide X-Tenant-ID header.",
            )

        request.state.tenant_id = tenant.id
        request.state.tenant = tenant
        return await call_next(request)



    # ============================================
    # Webhook: resolve from Meta payload
    # ============================================
    async def _resolve_from_webhook(self, request: Request) -> Tenant | None:
        """
        Extract phone_number_id from Meta's webhook payload
        and look up the corresponding tenant.

        Meta payload structure:
        {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {
                            "phone_number_id": "123456789"
                        }
                    }
                }]
            }]
        }
        """
        try:
            body = await request.json()

            phone_number_id = (
                body.get("entry", [{}])[0]
                .get("changes", [{}])[0]
                .get("value", {})
                .get("metadata", {})
                .get("phone_number_id")
            )

            if not phone_number_id:
                logger.warning("No phone_number_id found in webhook payload")
                return None

            async with async_session() as db:
                result = await db.execute(
                    select(Tenant).where(
                        Tenant.wa_phone_number_id == phone_number_id,
                        Tenant.is_active == True,
                    )
                )
                tenant = result.scalar_one_or_none()

            if tenant:
                logger.debug(
                    f"Tenant resolved: {tenant.name} "
                    f"(phone_number_id={phone_number_id})"
                )
            else:
                logger.warning(
                    f"No active tenant for phone_number_id={phone_number_id}"
                )

            return tenant

        except Exception as e:
            logger.exception(f"Error resolving tenant from webhook: {e}")
            return None

    # ============================================
    # Dashboard/API: resolve from header or JWT
    # ============================================
    async def _resolve_from_header(self, request: Request) -> Tenant | None:
        """
        Resolve tenant from X-Tenant-ID header (development).
        Will be replaced with JWT-based resolution in Week 7.
        """
        tenant_header = request.headers.get("X-Tenant-ID")

        if not tenant_header:
            return None

        try:
            tenant_uuid = UUID(tenant_header)
        except (ValueError, AttributeError):
            logger.warning(f"Invalid X-Tenant-ID header: {tenant_header}")
            return None

        async with async_session() as db:
            result = await db.execute(
                select(Tenant).where(
                    Tenant.id == tenant_uuid,
                    Tenant.is_active == True,
                )
            )
            return result.scalar_one_or_none()


# ============================================
# Utilities for route handlers
# ============================================
def get_tenant_id(request: Request) -> UUID:
    """
    Extract tenant_id from request state.
    Always returns a valid UUID — middleware guarantees it.
    """
    return request.state.tenant_id


def get_tenant(request: Request) -> Tenant:
    """
    Extract full tenant object from request state.
    """
    return request.state.tenant