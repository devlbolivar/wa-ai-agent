"""
Request Body Caching Middleware.
Caches the raw request body so it can be read multiple times
(once in TenantMiddleware, once in the route handler).

Must be added AFTER TenantMiddleware in the middleware stack
(last added = first executed in FastAPI).
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class BodyCacheMiddleware(BaseHTTPMiddleware):

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()

            async def cached_receive():
                return {"type": "http.request", "body": body}

            request._receive = cached_receive

        return await call_next(request)