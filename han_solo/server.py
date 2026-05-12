"""
Han Solo MCP Server — entry point.

Formal boundary between Claude (any tool, anywhere) and Han Solo's memory layer.
All reads and writes go through here. Claude never touches Letta directly.

Transport: Streamable HTTP (stateless) — endpoint at /mcp
Auth:      Bearer token per user, validated on every request
Deploy:    Render web service
"""
import contextlib
import logging

import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .auth import BearerAuthMiddleware
from .config import REN_AGENT_NAME
from . import letta_client as letta
from .tools import memory, signals, phase, brief, portraits
from . import chat_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP server — register all tool groups
# ---------------------------------------------------------------------------

# Disable built-in DNS rebinding protection — we enforce security via bearer token auth.
# Without this, FastMCP rejects requests from the Render hostname with 421.
_transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

server = FastMCP("han-solo", transport_security=_transport_security)

memory.register(server)
signals.register(server)
phase.register(server)
brief.register(server)
portraits.register(server)


# ---------------------------------------------------------------------------
# Health endpoint — no auth, for Render health check
# ---------------------------------------------------------------------------

async def health(request: Request) -> JSONResponse:
    agent_id = letta._ren_agent_id
    return JSONResponse({
        "status": "ok" if agent_id else "degraded",
        "ren_agent": agent_id or "not_initialised",
    })


# ---------------------------------------------------------------------------
# ASGI app
#
# FastMCP's streamable_http_app() creates a Starlette app with its own lifespan
# that initialises the SSE session manager's task group (required for streaming).
# We need BOTH lifespans to run — FastMCP's and ours (httpx client + Letta agent).
#
# Strategy:
#   1. Call streamable_http_app() to trigger lazy session manager creation.
#   2. Add the /health route directly to that Starlette app's router.
#   3. Replace the router's lifespan with a combined one that runs both.
#   4. Wrap with our raw ASGI auth middleware (avoids BaseHTTPMiddleware SSE breakage).
# ---------------------------------------------------------------------------

# Step 1 — get FastMCP's Starlette app (creates session_manager lazily)
_mcp_app = server.streamable_http_app()

# Step 2 — inject custom routes before the /mcp route
_chat_routes = [
    Route("/", chat_api.chat_index),
    Route("/health", health),
    Route("/api/me", chat_api.api_me),
    Route("/api/history", chat_api.api_history),
    Route("/api/send", chat_api.api_send, methods=["POST"]),
    Route("/api/memory-panel", chat_api.api_memory_panel),
]
for i, route in enumerate(_chat_routes):
    _mcp_app.router.routes.insert(i, route)


# Step 3 — combined lifespan: our setup + FastMCP's session manager
@contextlib.asynccontextmanager
async def _lifespan(app):
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        letta.set_client(client)
        logger.info("Resolving Ren agent '%s'...", REN_AGENT_NAME)
        try:
            agent_id = await letta.get_or_create_ren_agent(REN_AGENT_NAME)
            letta.set_ren_agent_id(agent_id)
            logger.info("Ren agent ready: %s", agent_id)
        except Exception as e:
            logger.error("Failed to initialise Ren agent (will retry on next request): %s", e)
        async with server.session_manager.run():
            yield


_mcp_app.router.lifespan_context = _lifespan

# Step 4 — raw ASGI auth middleware (preserves SSE streaming)
app = BearerAuthMiddleware(_mcp_app)
