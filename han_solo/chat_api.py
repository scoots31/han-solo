"""
Chat API — REST endpoints backing the Han Solo web UI.

Message history is backed by Letta's conversation store — survives restarts.
_history is a server-side cache rebuilt from Letta on first request after a
cold start, then kept current as new messages arrive.

Transcript capture: every message is written to the chat_transcripts table in
PostgreSQL as it arrives. This is the durable source that survives rollovers,
restarts, and context crashes. The synthesis script reads from here.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from .auth import get_current_user
from . import letta_client as letta
from . import db
from .app_html import APP_HTML
from .chat_html import CHAT_HTML
from .config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Message history cache — rebuilt from Letta on cold start
# ---------------------------------------------------------------------------

_history: list[dict] = []
_history_loaded: bool = False

# Session length thresholds. Each exchange = 2 entries (user + assistant).
# WARN_AT: surface a note in the UI so Scott can choose a clean stopping point.
# HARD_LIMIT_AT: safety rollover to prevent Letta context crashes — same as
#   what used to happen at 50, but pushed back and only fires if Scott doesn't
#   start a new session himself.
WARN_AT = 40
HARD_LIMIT_AT = 80

# Capture cadence: write to transcript table every N messages.
# Set to 1 to capture every message — safest, minimal DB overhead.
CAPTURE_EVERY_N = 5
_messages_since_last_capture: int = 0
_capture_buffer: list[dict] = []


def _push(name: str, text: str, role: str) -> dict:
    entry = {
        "role": role,
        "name": name,
        "text": text,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _history.append(entry)
    if len(_history) > 200:
        _history.pop(0)
    return entry


async def _ensure_history_loaded() -> None:
    """Populate _history from Letta on first call after a cold start."""
    global _history, _history_loaded
    if _history_loaded:
        return
    try:
        messages = await letta.list_chat_messages(limit=200)
        if messages:
            _history = messages[-200:]
    except Exception:
        pass  # fall back to empty — Letta may still be waking up
    _history_loaded = True


async def _capture_message(session_id: str, role: str, name: str, content: str) -> None:
    """
    Buffer a message and flush to the transcript table every CAPTURE_EVERY_N messages.
    Silent on failure — capture never blocks the chat.
    """
    global _messages_since_last_capture, _capture_buffer

    _capture_buffer.append({"role": role, "name": name, "content": content})
    _messages_since_last_capture += 1

    if _messages_since_last_capture >= CAPTURE_EVERY_N:
        to_write = _capture_buffer[:]
        _capture_buffer = []
        _messages_since_last_capture = 0
        success = await db.write_messages_bulk(session_id, to_write)
        if not db.health_status()["db_connected"]:
            pass  # DB not configured — expected in dev
        elif not success:
            # Put messages back so next flush catches them
            _capture_buffer = to_write + _capture_buffer


async def _flush_capture_buffer(session_id: str) -> None:
    """Flush any remaining buffered messages — called before rollover."""
    global _messages_since_last_capture, _capture_buffer
    if _capture_buffer:
        to_write = _capture_buffer[:]
        _capture_buffer = []
        _messages_since_last_capture = 0
        await db.write_messages_bulk(session_id, to_write)


async def _synthesize_handoff(messages: list[dict]) -> str | None:
    """
    Call Anthropic directly to produce a brief handoff summary of the current
    session. Written to pending_thoughts on the new agent so Ren has immediate
    context after a rollover — no 3-hour wait for the cron.

    Returns None if the API key is not set or the call fails.
    """
    if not ANTHROPIC_API_KEY or not messages:
        return None

    # Take the last 60 messages to keep the prompt bounded.
    recent = messages[-60:]
    transcript = "\n".join(
        f"{m.get('name', m.get('role', 'unknown'))}: {m.get('text', '')}"
        for m in recent
    )

    prompt = (
        "Summarize this conversation in 4-6 bullets. Cover: main topics discussed, "
        "decisions made, anything left unresolved, and anything Ren should surface "
        "at the start of the next session. Be specific — names, decisions, open threads. "
        "No preamble.\n\n"
        f"TRANSCRIPT:\n{transcript}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 600,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
    except Exception as e:
        logger.warning("Handoff synthesis failed — rollover continues without it: %s", e)
        return None


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

async def chat_index(request: Request) -> HTMLResponse:
    return HTMLResponse(APP_HTML)


async def chat_legacy(request: Request) -> HTMLResponse:
    return HTMLResponse(CHAT_HTML)


async def api_me(request: Request) -> JSONResponse:
    user = get_current_user()
    return JSONResponse({"name": user.name, "role": user.role.value, "id": user.id})


async def api_history(request: Request) -> JSONResponse:
    get_current_user()
    await _ensure_history_loaded()
    return JSONResponse(_history)


async def api_reset_session(request: Request) -> JSONResponse:
    """
    Manually start a fresh Letta conversation session.
    Synthesizes the current session inline so Ren wakes up with context,
    then archives the transcript buffer and creates a new agent.
    """
    global _history, _history_loaded
    get_current_user()
    try:
        current_id = await letta.ensure_ren_agent_id()
        await _flush_capture_buffer(current_id)
        summary = await _synthesize_handoff(_history)
        new_id = await letta.reset_conversation(handoff_summary=summary)
        _history = []
        _history_loaded = True
        return JSONResponse({"reset": True, "agent_id": new_id})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


async def api_send(request: Request) -> JSONResponse:
    global _history, _history_loaded

    user = get_current_user()
    body = await request.json()
    message = body.get("message", "").strip()
    attachment = body.get("attachment")  # {name, content} or None

    if not message and not attachment:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    # Warn at WARN_AT, hard rollover at HARD_LIMIT_AT.
    rolled_over = False
    session_warning = None
    history_len = len(_history)

    if history_len >= HARD_LIMIT_AT:
        try:
            current_id = await letta.ensure_ren_agent_id()
            await _flush_capture_buffer(current_id)
            summary = await _synthesize_handoff(_history)
            await letta.reset_conversation(handoff_summary=summary)
            _history = []
            _history_loaded = True
            rolled_over = True
        except Exception:
            pass  # rollover failed — continue on existing agent
    elif history_len == WARN_AT:
        session_warning = "Getting long — good time to start a new session at a natural stopping point."

    # Build the message Ren receives — inline file content when attached
    if attachment:
        name = attachment.get("name", "file")
        content = attachment.get("content", "")
        file_block = f"\n\n---\n📄 **{name}**\n```\n{content}\n```"
        letta_message = (message + file_block) if message else f"I'm sharing a file: {name}{file_block}"
        display_text = f"{message}\n\n📄 {name}" if message else f"📄 {name}"
    else:
        letta_message = message
        display_text = message

    session_id = await letta.ensure_ren_agent_id()

    _push(user.name, display_text, "user")
    asyncio.create_task(_capture_message(session_id, "user", user.name, display_text))

    try:
        response_text = await letta.send_chat_message(letta_message, user.name)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    if response_text:
        _push("Ren", response_text, "assistant")
        asyncio.create_task(_capture_message(session_id, "assistant", "Ren", response_text))

    return JSONResponse({
        "response": response_text,
        "session_reset": rolled_over,
        "session_warning": session_warning,
        "capture_health": db.health_status(),
    })


async def api_jobs_status(request: Request) -> JSONResponse:
    """Public endpoint — no auth required. Returns current jobs_paused state."""
    paused = await db.get_jobs_paused()
    return JSONResponse({"paused": paused})


async def api_set_jobs_paused(request: Request) -> JSONResponse:
    """Toggle automated jobs on/off. Requires auth."""
    get_current_user()
    body = await request.json()
    paused = bool(body.get("paused", False))
    ok = await db.set_jobs_paused(paused)
    if not ok:
        return JSONResponse({"error": "DB write failed"}, status_code=500)
    return JSONResponse({"paused": paused})


async def api_memory_panel(request: Request) -> JSONResponse:
    get_current_user()
    blocks = await letta.list_core_blocks()
    health = db.health_status()
    return JSONResponse({
        "blocks": [
            {
                "label": b.get("label"),
                "value": b.get("value", ""),
                "chars": len(b.get("value", "")),
            }
            for b in blocks
        ],
        "capture_health": health,
    })
