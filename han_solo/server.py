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
from .config import REN_AGENT_NAME, REN_AGENT_ID
from . import letta_client as letta
from . import db
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
async def admin_agent_info(request: Request) -> JSONResponse:
    agent_id = await letta.ensure_ren_agent_id()
    resp = await letta._letta("GET", f"{letta.LETTA_URL}/v1/agents/{agent_id}/")
    data = resp.json()
    return JSONResponse({
        "agent_id": agent_id,
        "name": data.get("name"),
        "llm_config": data.get("llm_config"),
    })


async def admin_patch_model(request: Request) -> JSONResponse:
    body = await request.json()
    model = body.get("model", "").strip()
    if not model:
        return JSONResponse({"error": "model required"}, status_code=400)
    result = await letta.patch_agent_model(model)
    return JSONResponse({"patched": True, "llm_config": result.get("llm_config")})


async def api_write_core_block(request: Request) -> JSONResponse:
    """REST endpoint for synthesis script to update a core memory block."""
    body = await request.json()
    label = body.get("label", "").strip()
    value = body.get("value", "")
    if not label:
        return JSONResponse({"error": "label required"}, status_code=400)
    try:
        result = await letta.write_core_block(label, value)
        return JSONResponse({"written": True, "label": label})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


async def api_write_signal_rest(request: Request) -> JSONResponse:
    """REST endpoint for synthesis script to write an archival signal."""
    from datetime import date as _date
    body = await request.json()
    signal_type = body.get("signal_type", "").strip()
    subject = body.get("subject", "").strip()
    content = body.get("content", "").strip()
    session_date = body.get("session_date", "") or _date.today().isoformat()

    if not all([signal_type, subject, content]):
        return JSONResponse({"error": "signal_type, subject, content required"}, status_code=400)

    valid_types = {"relational", "directional", "ren", "texture"}
    valid_subjects = {"scott", "ted", "ren", "project", "framework"}
    if signal_type not in valid_types or subject not in valid_subjects:
        return JSONResponse({"error": "invalid signal_type or subject"}, status_code=400)

    try:
        tags = ["signal", signal_type, subject, session_date, "author:synthesis"]
        result = await letta.insert_passage(content=content, tags=tags)
        return JSONResponse({"written": True, "id": result.get("id")})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


_chat_routes = [
    Route("/", chat_api.chat_index),
    Route("/health", health),
    Route("/api/me", chat_api.api_me),
    Route("/api/history", chat_api.api_history),
    Route("/api/send", chat_api.api_send, methods=["POST"]),
    Route("/api/reset-session", chat_api.api_reset_session, methods=["POST"]),
    Route("/api/memory-panel", chat_api.api_memory_panel),
    Route("/api/write-core-block", api_write_core_block, methods=["POST"]),
    Route("/api/write-signal", api_write_signal_rest, methods=["POST"]),
    Route("/api/admin/agent-info", admin_agent_info),
    Route("/api/admin/patch-model", admin_patch_model, methods=["POST"]),
]
for i, route in enumerate(_chat_routes):
    _mcp_app.router.routes.insert(i, route)


# Step 3 — combined lifespan: our setup + FastMCP's session manager
@contextlib.asynccontextmanager
async def _lifespan(app):
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
        letta.set_client(client)
        try:
            if REN_AGENT_ID:
                logger.info("Using pinned REN_AGENT_ID: %s", REN_AGENT_ID)
                letta.set_ren_agent_id(REN_AGENT_ID)
            else:
                logger.info("Resolving Ren agent '%s'...", REN_AGENT_NAME)
                agent_id = await letta.get_or_create_ren_agent(REN_AGENT_NAME)
                letta.set_ren_agent_id(agent_id)
                logger.info("Ren agent ready: %s", agent_id)
        except Exception as e:
            logger.error("Failed to initialise Ren agent (will retry on next request): %s", e)
        await db.init_pool()
        try:
            async with server.session_manager.run():
                yield
        finally:
            await db.close_pool()


_mcp_app.router.lifespan_context = _lifespan

# Step 4 — raw ASGI auth middleware (preserves SSE streaming)
app = BearerAuthMiddleware(_mcp_app)
