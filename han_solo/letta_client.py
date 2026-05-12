"""
Async client for Letta's REST API.
All Han Solo memory operations go through here — never call Letta directly from tools.
"""
from typing import Any, Optional
import logging
import httpx

from .config import LETTA_URL, LETTA_API_KEY, REN_AGENT_NAME

logger = logging.getLogger(__name__)

# Shared async client — initialised in server lifespan, closed on shutdown
_client: Optional[httpx.AsyncClient] = None

# Ren agent ID — resolved on first use; lazy so Letta sleeping at startup isn't fatal
_ren_agent_id: Optional[str] = None


def set_client(client: httpx.AsyncClient) -> None:
    global _client
    _client = client


def set_ren_agent_id(agent_id: str) -> None:
    global _ren_agent_id
    _ren_agent_id = agent_id


async def ensure_ren_agent_id() -> str:
    """Return the Ren agent ID, resolving it from Letta if not yet cached."""
    global _ren_agent_id
    if _ren_agent_id is not None:
        return _ren_agent_id
    logger.info("Ren agent ID not cached — resolving from Letta...")
    _ren_agent_id = await get_or_create_ren_agent(REN_AGENT_NAME)
    logger.info("Ren agent resolved: %s", _ren_agent_id)
    return _ren_agent_id


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {LETTA_API_KEY}",
        "Content-Type": "application/json",
    }


def _client_or_raise() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("HTTP client not initialised")
    return _client


# ---------------------------------------------------------------------------
# Agent bootstrap
# ---------------------------------------------------------------------------

async def get_or_create_ren_agent(name: str) -> str:
    """Return the agent_id for the named Ren agent, creating it if needed."""
    client = _client_or_raise()

    resp = await client.get(f"{LETTA_URL}/v1/agents", headers=_headers())
    resp.raise_for_status()
    agents = resp.json()

    for agent in agents:
        if agent.get("name") == name:
            return agent["id"]

    # Create a minimal Ren agent — memory blocks seeded separately
    payload = {
        "name": name,
        "agent_type": "memgpt_agent",
        "llm_config": {
            "model": "claude-sonnet-4-6",
            "model_endpoint_type": "anthropic",
            "context_window": 200000,
        },
        "embedding_config": {
            "embedding_endpoint_type": "anthropic",
            "embedding_model": "voyage-3",
            "embedding_dim": 1024,
        },
        "memory_blocks": [
            {"label": "always_loaded_core", "value": "", "limit": 10000},
            {"label": "pending_thoughts", "value": "", "limit": 5000},
            {"label": "project_state", "value": "{}", "limit": 10000},
        ],
    }
    resp = await client.post(f"{LETTA_URL}/v1/agents", headers=_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Core memory (Store 4 always-loaded blocks)
# ---------------------------------------------------------------------------

async def read_core_block(label: str) -> dict[str, Any]:
    client = _client_or_raise()
    agent_id = await ensure_ren_agent_id()
    resp = await client.get(
        f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks/{label}",
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def write_core_block(label: str, value: str) -> dict[str, Any]:
    client = _client_or_raise()
    agent_id = await ensure_ren_agent_id()
    resp = await client.patch(
        f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks/{label}",
        headers=_headers(),
        json={"value": value},
    )
    resp.raise_for_status()
    return resp.json()


async def list_core_blocks() -> list[dict[str, Any]]:
    client = _client_or_raise()
    agent_id = await ensure_ren_agent_id()
    resp = await client.get(
        f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks",
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def create_core_block(label: str, value: str = "", limit: int = 10000) -> dict[str, Any]:
    """Create a new memory block and attach it to the Ren agent."""
    client = _client_or_raise()
    agent_id = await ensure_ren_agent_id()

    # Create block
    resp = await client.post(
        f"{LETTA_URL}/v1/blocks",
        headers=_headers(),
        json={"label": label, "value": value, "limit": limit},
    )
    resp.raise_for_status()
    block = resp.json()

    # Attach to agent
    await client.patch(
        f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks/{label}",
        headers=_headers(),
        json={"value": value},
    )
    return block


# ---------------------------------------------------------------------------
# Archival memory (Store 4 signals, portraits — vector store)
# ---------------------------------------------------------------------------

async def insert_passage(content: str, tags: list[str]) -> dict[str, Any]:
    client = _client_or_raise()
    agent_id = await ensure_ren_agent_id()
    resp = await client.post(
        f"{LETTA_URL}/v1/agents/{agent_id}/passages",
        headers=_headers(),
        json={"text": content, "metadata_": {"tags": tags}},
    )
    resp.raise_for_status()
    return resp.json()


async def search_passages(query: str, limit: int = 20) -> list[dict[str, Any]]:
    client = _client_or_raise()
    agent_id = await ensure_ren_agent_id()
    resp = await client.get(
        f"{LETTA_URL}/v1/agents/{agent_id}/passages",
        headers=_headers(),
        params={"query_text": query, "limit": limit},
    )
    resp.raise_for_status()
    return resp.json()


async def list_passages(limit: int = 50) -> list[dict[str, Any]]:
    client = _client_or_raise()
    agent_id = await ensure_ren_agent_id()
    resp = await client.get(
        f"{LETTA_URL}/v1/agents/{agent_id}/passages",
        headers=_headers(),
        params={"limit": limit},
    )
    resp.raise_for_status()
    return resp.json()
