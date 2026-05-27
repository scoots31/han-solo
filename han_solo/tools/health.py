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

TIMEOUT = 5.0  # seconds per service check — fast enough not to stall session open


def register(server: FastMCP) -> None:

    @server.tool()
    async def check_system_health() -> dict:
        """
        Full health check across all system dependencies.

        Call at session start, after any tool failure, or on request.

        If all_healthy is False: surface to Scott immediately, pause work,
        and wait for team (Scott + Claude + Ren) to troubleshoot together.
        Do not proceed blindly. Do not diagnose solo.

        Checks (run in parallel):
        - letta: agent reachable, agent ID resolves, all 13 canonical tools attached
        - voyage_ai: embedding service reachable (connectivity only, no token burn)
        - anthropic: API key configured and /v1/models endpoint reachable
        - mcp_bridge: this server's /health endpoint responding
        - core_memory: pending_thoughts block readable from Letta

        Returns structured status per service, tools_attached count,
        recommendations list, and all_healthy flag.
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
                    status = "healthy" if not missing else "degraded"
                    return {
                        "status": status,
                        "details": f"{len(attached)} tools attached" if not missing
                                   else f"Missing tools: {', '.join(missing)}",
                        "agent_id": agent_id,
                        "tool_count": len(attached),
                        "missing_tools": missing,
                    }
            except Exception as e:
                return {"status": "unhealthy", "details": str(e)[:200]}

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
                        return {"status": "healthy", "details": f"HTTP {resp.status_code}"}
                    return {"status": "degraded", "details": f"HTTP {resp.status_code}"}
            except httpx.TimeoutException:
                return {"status": "unhealthy", "details": "timeout after 5s"}
            except Exception as e:
                return {"status": "unhealthy", "details": str(e)[:200]}

        async def _check_anthropic():
            if not ANTHROPIC_API_KEY:
                return {"status": "unconfigured", "details": "ANTHROPIC_API_KEY not set"}
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
                        return {"status": "healthy", "details": "API reachable"}
                    return {"status": "degraded", "details": f"HTTP {resp.status_code}"}
            except httpx.TimeoutException:
                return {"status": "unhealthy", "details": "timeout after 5s"}
            except Exception as e:
                return {"status": "unhealthy", "details": str(e)[:200]}

        async def _check_mcp_bridge():
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"http://localhost:{PORT}/health",
                        timeout=TIMEOUT,
                    )
                    if resp.status_code == 200:
                        return {"status": "healthy", "details": "bridge responding"}
                    return {"status": "degraded", "details": f"HTTP {resp.status_code}"}
            except Exception as e:
                return {"status": "unhealthy", "details": str(e)[:200]}

        async def _check_core_memory():
            try:
                block = await letta.read_core_block("pending_thoughts")
                value = block.get("value", "")
                return {"status": "healthy", "details": f"{len(value)} chars readable"}
            except Exception as e:
                return {"status": "unhealthy", "details": str(e)[:200]}

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

        recommendations = []
        if "letta" in unhealthy:
            recommendations.append("Letta unreachable — all memory tools will fail. Check han-solo-letta.onrender.com.")
        if "voyage_ai" in unhealthy:
            recommendations.append("Voyage AI down — archival_memory_search will fail. Check voyageai.com status.")
        if "anthropic" in unhealthy:
            recommendations.append("Anthropic API unreachable — model calls will fail. Check anthropic.com status.")
        if "mcp_bridge" in unhealthy:
            recommendations.append("MCP bridge self-ping failed — escalate to Claude immediately.")
        if "core_memory" in unhealthy:
            recommendations.append("Cannot read pending_thoughts — Letta may be degraded even if ping succeeded.")

        tools_attached = letta_r.get("tool_count", 0)

        return {
            "timestamp": timestamp,
            "all_healthy": all_healthy,
            "services": services,
            "tools_attached": tools_attached,
            "recommendations": recommendations if recommendations else ["All systems healthy — no action needed."],
        }
