from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import TOKEN_REGISTRY, UserIdentity

# Per-request user identity — set by auth middleware, read by tool handlers
_current_user: ContextVar[Optional[UserIdentity]] = ContextVar("current_user", default=None)


def get_current_user() -> UserIdentity:
    user = _current_user.get()
    if user is None:
        raise RuntimeError("No authenticated user in context")
    return user


def lookup_token(token: str) -> Optional[UserIdentity]:
    return TOKEN_REGISTRY.get(token)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """
    Validates Authorization: Bearer <token> on every request.
    Attaches the resolved UserIdentity to the request context variable.
    Exempts /health so Render's health check passes without a token.
    """

    EXEMPT_PATHS = {"/health", "/"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return Response("Unauthorized", status_code=401)

        token = auth_header.removeprefix("Bearer ").strip()
        user = lookup_token(token)
        if user is None:
            return Response("Forbidden", status_code=403)

        token_ctx = _current_user.set(user)
        try:
            response = await call_next(request)
        finally:
            _current_user.reset(token_ctx)

        return response
