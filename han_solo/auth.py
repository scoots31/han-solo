from contextvars import ContextVar
from typing import Optional

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

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


EXEMPT_PATHS = {"/health", "/", "/chat", "/workspace", "/api/jobs-status", "/api/session-logs"}


class BearerAuthMiddleware:
    """
    Raw ASGI middleware — avoids BaseHTTPMiddleware's response buffering,
    which breaks SSE streams used by MCP's Streamable HTTP transport.

    Validates Authorization: Bearer <token> on every request.
    Attaches the resolved UserIdentity to the request context variable.
    Exempts /health so Render's health check passes without a token.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in EXEMPT_PATHS or path.startswith("/docs/"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()

        if not auth_header.startswith("Bearer "):
            response = Response("Unauthorized", status_code=401)
            await response(scope, receive, send)
            return

        token = auth_header.removeprefix("Bearer ").strip()
        user = lookup_token(token)
        if user is None:
            response = Response("Forbidden", status_code=403)
            await response(scope, receive, send)
            return

        token_ctx = _current_user.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_user.reset(token_ctx)
