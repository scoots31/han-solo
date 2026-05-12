"""
Han Solo MCP Server — entry point.

Serves as the formal boundary between Claude (in any tool, anywhere) and Han Solo's
memory layer. All reads and writes go through here. Claude never touches Letta directly.

Transport: Streamable HTTP (stateless) — one endpoint at /mcp
Auth:      Bearer token per user, validated on every request
Deploy:    Render web service, PORT env var
"""
import contextlib
import logging

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP

from .auth import BearerAuthMiddleware
from .config import LETTA_URL, LETTA_API_KEY, PORT, REN_AGENT_NAME
from . import letta_client as letta

from .tools.memory import mcp as memory_mcp
from .tools.signals import mcp as signals_mcp
from .tools.phase import mcp as phase_mcp
from .tools.brief import mcp as brief_mcp
from .tools.portraits import mcp as portraits_mcp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Main MCP server — all tools registered here
# ---------------------------------------------------------------------------

server = FastMCP("han-solo")

# Mount each tool group by importing and re-registering their tools
for tool in memory_mcp._tool_manager.list_tools():
    server._tool_manager.add_tool(tool)

for tool in signals_mcp._tool_manager.list_tools():
    server._tool_manager.add_tool(tool)

for tool in phase_mcp._tool_manager.list_tools():
    server._tool_manager.add_tool(tool)

for tool in brief_mcp._tool_manager.list_tools():
    server._tool_manager.add_tool(tool)

for tool in portraits_mcp._tool_manager.list_tools():
    server._tool_manager.add_tool(tool)


# ---------------------------------------------------------------------------
# Lifespan — initialise shared resources on startup
# ---------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def lifespan(app):
    # Shared async HTTP client for all Letta calls
    async with httpx.AsyncClient(timeout=30.0) as client:
        letta.set_client(client)

        # Resolve/create the Ren agent
        logger.info("Resolving Ren agent '%s'...", REN_AGENT_NAME)
        try:
            agent_id = await letta.get_or_create_ren_agent(REN_AGENT_NAME)
            letta.set_ren_agent_id(agent_id)
            logger.info("Ren agent ready: %s", agent_id)
        except Exception as e:
            logger.error("Failed to initialise Ren agent: %s", e)
            raise

        yield


# ---------------------------------------------------------------------------
# Health endpoint (no auth — Render health check)
# ---------------------------------------------------------------------------

async def health(request: Request) -> JSONResponse:
    agent_id = letta._ren_agent_id or "not_initialised"
    return JSONResponse({"status": "ok", "ren_agent": agent_id})


# ---------------------------------------------------------------------------
# ASGI app — MCP mounted at /mcp, health at /health
# ---------------------------------------------------------------------------

app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/health", health),
        Mount("/mcp", app=server.streamable_http_app()),
    ],
)

app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mcp.server:app", host="0.0.0.0", port=PORT, reload=False)
