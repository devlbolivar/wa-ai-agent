"""
Request Body Caching Middleware.
Caches the raw request body so it can be read multiple times
(once in TenantMiddleware, once in the route handler).

Must be added BEFORE TenantMiddleware in the middleware stack.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class BodyCacheMiddleware(BaseHTTPMiddleware):
    """
    Reads and caches the request body on first access.
    Subsequent calls to request.json() or request.body()
    return the cached version.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Only cache for POST/PUT/PATCH requests
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            request.state._cached_body = body

            # Override the receive function to return cached body
            async def cached_receive():
                return {"type": "http.request", "body": body}

            request._receive = cached_receive

        return await call_next(request)