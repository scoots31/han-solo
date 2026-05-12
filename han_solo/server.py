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

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .auth import BearerAuthMiddleware
from .config import REN_AGENT_NAME
from . import letta_client as letta
from .tools import memory, signals, phase, brief, portraits

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP server — register all tool groups
# ---------------------------------------------------------------------------

server = FastMCP("han-solo")

memory.register(server)
signals.register(server)
phase.register(server)
brief.register(server)
portraits.register(server)


# ---------------------------------------------------------------------------
# Lifespan — shared resources
# ---------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=30.0) as client:
        letta.set_client(client)
        logger.info("Resolving Ren agent '%s'...", REN_AGENT_NAME)
        try:
            agent_id = await letta.get_or_create_ren_agent(REN_AGENT_NAME)
            letta.set_ren_agent_id(agent_id)
            logger.info("Ren agent ready: %s", agent_id)
        except Exception as e:
            # Log but don't crash — server stays up, tools will fail gracefully
            # until Letta is reachable. Health check reports degraded state.
            logger.error("Failed to initialise Ren agent (will retry on next request): %s", e)
        yield


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
# ---------------------------------------------------------------------------

app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/health", health),
        Mount("/mcp", app=server.streamable_http_app()),
    ],
)

app.add_middleware(BearerAuthMiddleware)
