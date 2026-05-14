"""
Async client for Letta's REST API.
All Han Solo memory operations go through here — never call Letta directly from tools.
"""
from typing import Any, Optional
import logging
import httpx

from .config import LETTA_URL, LETTA_API_KEY, REN_AGENT_NAME, REN_AGENT_ID
from . import db as _db

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
    """Return the Ren agent ID, resolving it from DB → env var → Letta lookup."""
    global _ren_agent_id
    if _ren_agent_id is not None:
        return _ren_agent_id
    # DB is authoritative after any rollover — check it first so restarts
    # wake up as the correct rolled-over agent, not the env-pinned baseline.
    db_id = await _db.get_active_agent_id()
    if db_id:
        logger.info("Using persisted active_agent_id from DB: %s", db_id)
        _ren_agent_id = db_id
        return _ren_agent_id
    # Fall back to env var (used on first deploy before any rollover).
    if REN_AGENT_ID:
        logger.info("Using pinned REN_AGENT_ID: %s", REN_AGENT_ID)
        _ren_agent_id = REN_AGENT_ID
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


async def _letta(method: str, url: str, timeout: float = 60.0, **kwargs) -> httpx.Response:
    """
    Make a request to Letta with auth, following redirects manually.

    Render's reverse proxy emits http:// in Location headers even for https
    services. httpx strips Authorization on https→http scheme downgrades.
    We follow the redirect ourselves, converting http:// back to https://.
    """
    client = _client_or_raise()
    resp = await client.request(
        method, url, headers=_headers(), follow_redirects=False,
        timeout=timeout, **kwargs
    )
    if resp.is_redirect:
        location = resp.headers.get("location", "")
        # Fix Render's http→https scheme artifact before retrying
        location = location.replace("http://", "https://", 1)
        logger.debug("Redirect %s → %s", url, location)
        resp = await client.request(
            method, location, headers=_headers(), follow_redirects=False,
            timeout=timeout, **kwargs
        )
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# Agent bootstrap
# ---------------------------------------------------------------------------

async def get_or_create_ren_agent(name: str) -> str:
    """
    Return the agent_id for the active Ren agent.

    Priority:
      1. Exact name match (handles initial setup and env-var-configured names).
      2. Most recently created agent whose name starts with "ren-" (handles session
         rollovers where the active agent has a timestamp name).
      3. Create a minimal new agent if none found.
    """
    resp = await _letta("GET", f"{LETTA_URL}/v1/agents")
    agents = resp.json()

    # 1. Exact match
    for agent in agents:
        if agent.get("name") == name:
            return agent["id"]

    # 2. Most recent versioned "ren-v*" agent only — session agents (ren-session-*)
    # are ephemeral and should not survive a server cold restart.
    ren_agents = [a for a in agents if a.get("name", "").startswith("ren-v")]
    if ren_agents:
        ren_agents.sort(key=lambda a: a.get("created_at", ""), reverse=True)
        found = ren_agents[0]
        logger.info("Exact name '%s' not found; using most recent versioned ren agent: %s (%s)",
                    name, found["name"], found["id"])
        return found["id"]

    # 3. Create minimal agent — memory blocks seeded separately
    payload = {
        "name": name,
        "agent_type": "memgpt_agent",
        "llm_config": {
            "model": "claude-haiku-4-5-20251001",
            "model_endpoint_type": "anthropic",
            "context_window": 200000,
        },
        "embedding_config": {
            "embedding_endpoint_type": "openai",
            "embedding_endpoint": "https://api.voyageai.com/v1",
            "embedding_model": "voyage-3",
            "embedding_dim": 1024,
        },
        "memory_blocks": [
            {"label": "always_loaded_core", "value": "", "limit": 10000},
            {"label": "pending_thoughts", "value": "", "limit": 8000},
            {"label": "project_state", "value": "{}", "limit": 10000},
        ],
    }
    resp = await _letta("POST", f"{LETTA_URL}/v1/agents", json=payload)
    return resp.json()["id"]


async def reset_conversation() -> str:
    """
    Create a fresh Letta agent with all core memory blocks copied from the
    current agent. Updates the cached agent ID so subsequent calls use the
    new agent. Returns the new agent ID.

    The old agent is left intact — its conversation history remains readable
    for recovery if needed.
    """
    global _ren_agent_id
    import time

    current_id = await ensure_ren_agent_id()

    # Read current agent config and blocks
    config_resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{current_id}")
    current = config_resp.json()

    blocks_resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{current_id}/core-memory/blocks")
    blocks = blocks_resp.json()

    new_name = f"ren-session-{int(time.time())}"
    tool_ids = [t["id"] for t in current.get("tools", [])]

    # Always pin the model — never inherit a potentially drifted config
    llm_config = current["llm_config"].copy()
    llm_config["model"] = "claude-haiku-4-5-20251001"

    payload = {
        "name": new_name,
        "agent_type": "memgpt_agent",
        "llm_config": llm_config,
        "embedding_config": current["embedding_config"],
        "system": current.get("system", ""),
        "tool_ids": tool_ids,
        "memory_blocks": [
            {"label": b["label"], "value": b["value"], "limit": b["limit"]}
            for b in blocks
        ],
    }

    new_resp = await _letta("POST", f"{LETTA_URL}/v1/agents", json=payload, timeout=90.0)
    new_id = new_resp.json()["id"]
    _ren_agent_id = new_id

    # Persist so restarts wake up as this agent, not the env-pinned baseline.
    await _db.set_active_agent_id(new_id)

    # Append a rollover marker to pending_thoughts on the new agent so Ren
    # knows a rollover just happened even before synthesis runs.
    rollover_note = (
        f"\n---\nROLLOVER [{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}]: "
        f"Continued from agent {current_id}. Raw transcript saved to DB. "
        f"Synthesis will process within 3 hours."
    )
    try:
        pt_resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{new_id}/core-memory/blocks/pending_thoughts")
        current_pt = pt_resp.json().get("value", "")
        await _letta(
            "PATCH",
            f"{LETTA_URL}/v1/agents/{new_id}/core-memory/blocks/pending_thoughts",
            json={"value": current_pt + rollover_note},
        )
    except Exception as e:
        logger.warning("Could not append rollover note to pending_thoughts: %s", e)

    logger.info("Session rolled over: %s → %s (%s)", current_id, new_name, new_id)
    return new_id


async def patch_agent_model(model: str) -> dict[str, Any]:
    """Patch the active Ren agent's LLM model. One-time admin use."""
    agent_id = await ensure_ren_agent_id()
    config_resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}")
    current = config_resp.json()
    llm_config = current["llm_config"]
    llm_config["model"] = model
    resp = await _letta("PATCH", f"{LETTA_URL}/v1/agents/{agent_id}", json={"llm_config": llm_config})
    return resp.json()


# ---------------------------------------------------------------------------
# Core memory (Store 4 always-loaded blocks)
# ---------------------------------------------------------------------------

async def read_core_block(label: str) -> dict[str, Any]:
    agent_id = await ensure_ren_agent_id()
    resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks/{label}")
    return resp.json()


async def write_core_block(label: str, value: str) -> dict[str, Any]:
    agent_id = await ensure_ren_agent_id()
    resp = await _letta("PATCH", f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks/{label}", json={"value": value})
    return resp.json()


async def list_core_blocks() -> list[dict[str, Any]]:
    agent_id = await ensure_ren_agent_id()
    resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks")
    return resp.json()


async def create_core_block(label: str, value: str = "", limit: int = 10000) -> dict[str, Any]:
    """Create a new memory block and attach it to the Ren agent."""
    agent_id = await ensure_ren_agent_id()

    resp = await _letta("POST", f"{LETTA_URL}/v1/blocks", json={"label": label, "value": value, "limit": limit})
    block = resp.json()

    await _letta("PATCH", f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks/{label}", json={"value": value})
    return block


# ---------------------------------------------------------------------------
# Archival memory (Store 4 signals, portraits — vector store)
# ---------------------------------------------------------------------------

async def insert_passage(content: str, tags: list[str]) -> dict[str, Any]:
    agent_id = await ensure_ren_agent_id()
    resp = await _letta("POST", f"{LETTA_URL}/v1/agents/{agent_id}/archival-memory", json={"text": content})
    data = resp.json()
    return data[0] if isinstance(data, list) else data


async def search_passages(query: str, limit: int = 20) -> list[dict[str, Any]]:
    agent_id = await ensure_ren_agent_id()
    resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}/archival-memory", params={"query_text": query, "limit": limit})
    return resp.json()


async def list_passages(limit: int = 50) -> list[dict[str, Any]]:
    agent_id = await ensure_ren_agent_id()
    resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}/archival-memory", params={"limit": limit})
    return resp.json()


# ---------------------------------------------------------------------------
# Chat history — read conversation messages from Letta
# ---------------------------------------------------------------------------

async def list_chat_messages(limit: int = 200) -> list[dict[str, Any]]:
    """
    Fetch recent conversation messages from Letta and return them in the
    same shape as chat_api._history: {role, name, text, ts}.

    Filters to user_message and assistant_message types only — skips
    reasoning, tool calls, and system messages.
    """
    agent_id = await ensure_ren_agent_id()
    resp = await _letta(
        "GET",
        f"{LETTA_URL}/v1/agents/{agent_id}/messages",
        params={"limit": limit},
    )
    raw = resp.json()
    # Letta may return {"messages": [...]} or a bare list
    messages = raw.get("messages", raw) if isinstance(raw, dict) else raw

    result = []
    for msg in messages:
        mtype = msg.get("message_type", "")
        if mtype == "user_message":
            result.append({
                "role": "user",
                "name": msg.get("name") or "Scott",
                "text": msg.get("content") or msg.get("text", ""),
                "ts": msg.get("created_at", ""),
            })
        elif mtype == "assistant_message":
            result.append({
                "role": "assistant",
                "name": "Ren",
                "text": msg.get("content") or msg.get("assistant_message", ""),
                "ts": msg.get("created_at", ""),
            })
    return result


# ---------------------------------------------------------------------------
# Chat — send a message and get Ren's response
# ---------------------------------------------------------------------------

async def send_chat_message(content: str, user_name: str) -> str:
    """Send a message to the Ren agent, return the assistant's text response."""
    agent_id = await ensure_ren_agent_id()
    payload = {
        "messages": [{"role": "user", "content": content, "name": user_name}],
        "stream_tokens": False,
    }
    resp = await _letta("POST", f"{LETTA_URL}/v1/agents/{agent_id}/messages", json=payload, timeout=180.0)
    data = resp.json()
    for msg in data.get("messages", []):
        if msg.get("message_type") == "assistant_message":
            return msg.get("content", "") or msg.get("assistant_message", "")
    return ""
