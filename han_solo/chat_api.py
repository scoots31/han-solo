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
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from .auth import get_current_user
from . import letta_client as letta
from . import db
from .chat_html import CHAT_HTML

# ---------------------------------------------------------------------------
# Message history cache — rebuilt from Letta on cold start
# ---------------------------------------------------------------------------

_history: list[dict] = []
_history_loaded: bool = False

# Auto-rollover: reset Letta session when conversation grows this long.
# Each exchange is 2 entries (user + assistant). 50 entries ≈ 25 exchanges.
# Keeps well clear of the 200K-token context limit even with heavy page fetches.
AUTO_ROLLOVER_AT = 50

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


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

async def chat_index(request: Request) -> HTMLResponse:
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
    Archives current transcript buffer, copies all core memory blocks to a
    new agent, clears the history cache.
    """
    global _history, _history_loaded
    get_current_user()
    try:
        current_id = await letta.ensure_ren_agent_id()
        await _flush_capture_buffer(current_id)
        new_id = await letta.reset_conversation()
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

    # Auto-rollover: archive transcript buffer first, then reset.
    rolled_over = False
    if len(_history) >= AUTO_ROLLOVER_AT:
        try:
            current_id = await letta.ensure_ren_agent_id()
            await _flush_capture_buffer(current_id)
            await letta.reset_conversation()
            _history = []
            _history_loaded = True
            rolled_over = True
        except Exception:
            pass  # rollover failed — continue on existing agent

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
        "capture_health": db.health_status(),
    })


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
