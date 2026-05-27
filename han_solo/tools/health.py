"""
System health check — Ren calls this at session start, on tool failure, or on request.
Returns structured status for all services and agent state. Does not block.
"""
import asyncio
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from ..config import LETTA_URL, LETTA_API_KEY, ANTHROPIC_API_KEY, PORT
from .. import letta_client as letta
from ..letta_client import CANONICAL_REN_TOOL_NAMES

TIMEOUT = 5.0  # seconds per service; fast enough to not stall session open


def register(server: FastMCP) -> None:

    @server.tool()
    async def check_system_health() -> dict:
        """
        Full health check across all system dependencies.

        Run at session start, after any tool failure, or on request.
        Does NOT block — surface failures and continue.

        Checks:
        - letta: agent reachable, agent ID resolves, all canonical tools attached
        - voyage_ai: embedding service reachable (connectivity only — no token burn)
        - anthropic: API key configured and /v1/models endpoint reachable
        - mcp_bridge: this server's /health endpoint responding
        - core_memory: pending_thoughts block readable from Letta

        Returns all_healthy (bool), per-service status, and a plain-language action line.
        """
        get_current_user()
        timestamp = datetime.now(timezone.utc).isoformat()

        async def _check_letta():
            try:
                agent_id = await letta.ensure_ren_agent_id()
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{LETTA_URL}/v1/agents/{agent_id}",
                        headers={"Authorization": f"Bearer {LETTA_API_KEY}"},
                        follow_redirects=True,
                        timeout=TIMEOUT,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    attached = {t["name"] for t in data.get("tools", [])}
                    missing = sorted(CANONICAL_REN_TOOL_NAMES - attached)
                    return {
                        "status": "healthy" if not missing else "degraded",
                        "agent_id": agent_id,
                        "tool_count": len(attached),
                        "expected_tool_count": len(CANONICAL_REN_TOOL_NAMES),
                        "missing_tools": missing,
                    }
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)[:200]}

        async def _check_voyage_ai():
            # Connectivity check only — any HTTP response means the service is up.
            # 401/403/405 = up but auth required. Timeout/connection error = down.
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.head(
                        "https://api.voyageai.com/v1/embeddings",
                        timeout=TIMEOUT,
                    )
                    if resp.status_code < 500:
                        return {"status": "healthy", "http_status": resp.status_code}
                    return {"status": "degraded", "http_status": resp.status_code}
            except httpx.TimeoutException:
                return {"status": "unhealthy", "error": "timeout"}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)[:200]}

        async def _check_anthropic():
            if not ANTHROPIC_API_KEY:
                return {"status": "unconfigured", "error": "ANTHROPIC_API_KEY not set"}
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://api.anthropic.com/v1/models",
                        headers={
                            "x-api-key": ANTHROPIC_API_KEY,
                            "anthropic-version": "2023-06-01",
                        },
                        timeout=TIMEOUT,
                    )
                    if resp.status_code == 200:
                        return {"status": "healthy"}
                    return {"status": "degraded", "http_status": resp.status_code}
            except httpx.TimeoutException:
                return {"status": "unhealthy", "error": "timeout"}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)[:200]}

        async def _check_mcp_bridge():
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"http://localhost:{PORT}/health",
                        timeout=TIMEOUT,
                    )
                    if resp.status_code == 200:
                        return {"status": "healthy"}
                    return {"status": "degraded", "http_status": resp.status_code}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)[:200]}

        async def _check_core_memory():
            try:
                block = await letta.read_core_block("pending_thoughts")
                value = block.get("value", "")
                return {"status": "healthy", "chars": len(value)}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)[:200]}

        # All checks run in parallel — total wall time capped at TIMEOUT
        letta_r, voyage_r, anthropic_r, bridge_r, memory_r = await asyncio.gather(
            _check_letta(),
            _check_voyage_ai(),
            _check_anthropic(),
            _check_mcp_bridge(),
            _check_core_memory(),
        )

        services = {
            "letta": letta_r,
            "voyage_ai": voyage_r,
            "anthropic": anthropic_r,
            "mcp_bridge": bridge_r,
            "core_memory": memory_r,
        }

        all_healthy = all(v.get("status") == "healthy" for v in services.values())
        unhealthy = [k for k, v in services.items() if v.get("status") != "healthy"]

        return {
            "timestamp": timestamp,
            "all_healthy": all_healthy,
            "unhealthy_services": unhealthy,
            "services": services,
            "action": (
                "All systems healthy."
                if all_healthy
                else f"Degraded: {', '.join(unhealthy)}. Surface to Scott before proceeding with work."
            ),
        }
