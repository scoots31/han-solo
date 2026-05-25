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

# Canonical tool set for the Ren agent — restored on every server startup.
# If a tool is missing (e.g. after a Letta PATCH that omitted tool_ids),
# ensure_ren_tools() re-attaches it from the Letta tool registry.
CANONICAL_REN_TOOL_NAMES = {
    "search_t4", "get_t4_entry", "search_signals", "get_session_brief",
    "list_notecards", "get_skill", "list_skills", "write_skill",
    "write_t4_entry", "search_transcripts", "search_code",
}

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


async def reset_conversation(handoff_summary: str | None = None) -> str:
    """
    Clear the conversation history on the current agent (same agent, same memory).
    Writes handoff summary to pending_thoughts first so Ren has context after reset.
    Returns the agent ID (unchanged).
    """
    import time

    agent_id = await ensure_ren_agent_id()
    timestamp = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())

    # Write handoff context to pending_thoughts before clearing messages.
    if handoff_summary:
        rollover_note = (
            f"\n---\nNEW SESSION [{timestamp}]:\n{handoff_summary}"
        )
    else:
        rollover_note = (
            f"\n---\nNEW SESSION [{timestamp}]: Context window cleared. "
            f"Raw transcript saved to DB. Synthesis will process within 3 hours."
        )
    try:
        pt_resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks/pending_thoughts")
        current_pt = pt_resp.json().get("value", "")
        await _letta(
            "PATCH",
            f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks/pending_thoughts",
            json={"value": current_pt + rollover_note},
        )
    except Exception as e:
        logger.warning("Could not write session note to pending_thoughts: %s", e)

    # Clear message history — same agent, core blocks and archival memory untouched.
    await _letta("PATCH", f"{LETTA_URL}/v1/agents/{agent_id}/reset-messages", json={})
    logger.info("Session reset on agent %s — memory intact", agent_id)
    return agent_id


async def patch_agent_model(model: str, enable_reasoner: bool = False) -> dict[str, Any]:
    """Patch the active Ren agent's LLM model.

    Resolves canonical tool IDs from the Letta registry — never trusts the
    agent's current tool state, which may be empty if a prior PATCH wiped tools.
    Every model switch atomically restores the full canonical tool set.
    """
    agent_id = await ensure_ren_agent_id()
    config_resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}")
    current = config_resp.json()
    llm_config = current["llm_config"]
    llm_config["model"] = model
    llm_config["enable_reasoner"] = enable_reasoner

    # Resolve canonical tool IDs from the registry — authoritative source.
    tools_resp = await _letta("GET", f"{LETTA_URL}/v1/tools?limit=200")
    all_tools = {t["name"]: t["id"] for t in tools_resp.json()}
    canonical_tool_ids = [all_tools[name] for name in CANONICAL_REN_TOOL_NAMES if name in all_tools]

    resp = await _letta("PATCH", f"{LETTA_URL}/v1/agents/{agent_id}", json={
        "llm_config": llm_config,
        "tool_ids": canonical_tool_ids,
    })
    return resp.json()


async def patch_agent_system(system: str) -> dict[str, Any]:
    """Patch the active Ren agent's system prompt.

    Atomically updates system + restores canonical tool set from registry.
    Never trusts the agent's current tool state.
    """
    agent_id = await ensure_ren_agent_id()
    config_resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}")
    current = config_resp.json()
    llm_config = current["llm_config"]

    tools_resp = await _letta("GET", f"{LETTA_URL}/v1/tools?limit=200")
    all_tools = {t["name"]: t["id"] for t in tools_resp.json()}
    canonical_tool_ids = [all_tools[name] for name in CANONICAL_REN_TOOL_NAMES if name in all_tools]

    resp = await _letta("PATCH", f"{LETTA_URL}/v1/agents/{agent_id}", json={
        "system": system,
        "llm_config": llm_config,
        "tool_ids": canonical_tool_ids,
    })
    return resp.json()


async def ensure_ren_tools() -> None:
    """Ensure Ren's canonical tools are all attached. Called at server startup.

    Letta's PATCH /v1/agents/{id} resets tool_ids to empty when the field is
    omitted — any model switch that doesn't include tool_ids will wipe tools.
    This function runs at startup to catch and repair that silently.
    """
    try:
        agent_id = await ensure_ren_agent_id()
        agent_resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}")
        agent = agent_resp.json()
        current_tools = {t["name"]: t["id"] for t in agent.get("tools", [])}

        if CANONICAL_REN_TOOL_NAMES.issubset(current_tools.keys()):
            logger.info("Ren tools OK — %d attached", len(current_tools))
            return

        missing = CANONICAL_REN_TOOL_NAMES - current_tools.keys()
        logger.warning("Ren is missing %d tools: %s — restoring...", len(missing), missing)

        tools_resp = await _letta("GET", f"{LETTA_URL}/v1/tools?limit=200")
        all_tools = tools_resp.json()
        available = {t["name"]: t["id"] for t in all_tools}

        target_ids = list(current_tools.values())
        restored = []
        for name in CANONICAL_REN_TOOL_NAMES:
            if name not in current_tools and name in available:
                target_ids.append(available[name])
                restored.append(name)

        if restored:
            await _letta("PATCH", f"{LETTA_URL}/v1/agents/{agent_id}", json={"tool_ids": target_ids})
            logger.info("Restored %d tools to Ren: %s", len(restored), restored)
        else:
            still_missing = CANONICAL_REN_TOOL_NAMES - set(available.keys())
            logger.error("Cannot restore tools — not found in Letta registry: %s", still_missing)
    except Exception as e:
        logger.error("ensure_ren_tools failed (non-fatal): %s", e)


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
    """Create a new memory block in Letta's global store and attach it to the Ren agent.

    Letta attach endpoint: PATCH /v1/agents/{id}/core-memory/blocks/attach/{block_id}
    The old PATCH-by-label approach fails for blocks not yet part of the agent's memory.
    """
    agent_id = await ensure_ren_agent_id()

    resp = await _letta("POST", f"{LETTA_URL}/v1/blocks", json={"label": label, "value": value, "limit": limit})
    block = resp.json()
    block_id = block["id"]

    await _letta("PATCH", f"{LETTA_URL}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}")
    return block


# ---------------------------------------------------------------------------
# Archival memory (Store 4 signals, portraits — vector store)
# ---------------------------------------------------------------------------

async def insert_passage(content: str, tags: list[str]) -> dict[str, Any]:
    agent_id = await ensure_ren_agent_id()
    resp = await _letta("POST", f"{LETTA_URL}/v1/agents/{agent_id}/archival-memory", json={"text": content})
    data = resp.json()
    return data[0] if isinstance(data, list) else data


# NOTE: This function exists and works — Voyage AI embeddings, pgvector, semantic search.
# It is NOT yet exposed as an MCP tool that Ren or Claude Code can call directly.
# Exposing it is the next step for T2/T3 retrieval — the infrastructure is ready.
async def search_passages(query: str, limit: int = 20) -> list[dict[str, Any]]:
    agent_id = await ensure_ren_agent_id()
    resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}/archival-memory", params={"query_text": query, "limit": limit})
    return resp.json()


async def list_passages(limit: int = 50) -> list[dict[str, Any]]:
    agent_id = await ensure_ren_agent_id()
    resp = await _letta("GET", f"{LETTA_URL}/v1/agents/{agent_id}/archival-memory", params={"limit": limit})
    return resp.json()


async def delete_passage(passage_id: str) -> None:
    agent_id = await ensure_ren_agent_id()
    await _letta("DELETE", f"{LETTA_URL}/v1/agents/{agent_id}/archival-memory/{passage_id}")


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

async def send_chat_message(content: str, user_name: str) -> tuple[list[str], bool, dict]:
    """
    Send a message to the Ren agent.

    Returns (messages, wants_to_continue, usage) where:
    - messages: list of send_message calls Ren made (rendered as separate bubbles)
    - wants_to_continue: True if Ren has more to say next turn
    - usage: dict with prompt_tokens, completion_tokens, total_tokens, context_tokens,
             cached_input_tokens, step_count

    Ren signals continuation by appending [[CONTINUES]] to her last message.
    """
    agent_id = await ensure_ren_agent_id()
    payload = {
        "messages": [{"role": "user", "content": content, "name": user_name}],
        "stream_tokens": False,
    }
    resp = await _letta("POST", f"{LETTA_URL}/v1/agents/{agent_id}/messages", json=payload, timeout=180.0)
    data = resp.json()

    # Collect the single assistant_message Letta returns per step.
    # Ren uses [[MSG]] to separate multiple logical bubbles within one send_message call,
    # and [[CONTINUES]] at the end to signal she has more to say next turn.
    raw = ""
    for msg in data.get("messages", []):
        if msg.get("message_type") == "assistant_message":
            raw = msg.get("content", "") or msg.get("assistant_message", "")
            break  # Letta only emits one per step

    wants_to_continue = False
    if "[[CONTINUES]]" in raw:
        wants_to_continue = True
        raw = raw.replace("[[CONTINUES]]", "").strip()

    # Split on [[MSG]] to produce separate bubbles
    messages = [m.strip() for m in raw.split("[[MSG]]") if m.strip()]

    # Extract usage statistics — present in every Letta response
    u = data.get("usage", {})
    usage = {
        "prompt_tokens": u.get("prompt_tokens", 0),
        "completion_tokens": u.get("completion_tokens", 0),
        "total_tokens": u.get("total_tokens", 0),
        "context_tokens": u.get("context_tokens"),
        "cached_input_tokens": u.get("cached_input_tokens"),
        "step_count": u.get("step_count", 0),
    }

    return messages, wants_to_continue, usage
