"""
Chat API — REST endpoints backing the Han Solo web UI.

Message history is backed by Letta's conversation store — survives restarts.
_history is a server-side cache rebuilt from Letta on first request after a
cold start, then kept current as new messages arrive.
"""
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from .auth import get_current_user
from . import letta_client as letta
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
    Copies all core memory blocks to a new agent; clears the history cache.
    """
    global _history, _history_loaded
    get_current_user()
    try:
        new_id = await letta.reset_conversation()
        _history = []
        _history_loaded = True  # skip Letta rebuild — we know it's empty
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

    # Auto-rollover: if conversation is getting long, reset before this message
    # so it goes to a fresh agent with no context pressure.
    rolled_over = False
    if len(_history) >= AUTO_ROLLOVER_AT:
        try:
            await letta.reset_conversation()
            _history = []
            _history_loaded = True
            rolled_over = True
        except Exception:
            pass  # rollover failed — continue on existing agent rather than dropping the message

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

    _push(user.name, display_text, "user")

    try:
        response_text = await letta.send_chat_message(letta_message, user.name)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    if response_text:
        _push("Ren", response_text, "assistant")

    return JSONResponse({"response": response_text, "session_reset": rolled_over})


async def api_admin_set_model(request: Request) -> JSONResponse:
    get_current_user()
    body = await request.json()
    model = body.get("model", "").strip()
    if not model:
        return JSONResponse({"error": "model required"}, status_code=400)
    try:
        result = await letta.patch_agent_model(model)
        return JSONResponse({"ok": True, "agent_id": result.get("id"), "model": model})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


async def api_memory_panel(request: Request) -> JSONResponse:
    get_current_user()
    blocks = await letta.list_core_blocks()
    return JSONResponse([
        {
            "label": b.get("label"),
            "value": b.get("value", ""),
            "chars": len(b.get("value", "")),
        }
        for b in blocks
    ])
