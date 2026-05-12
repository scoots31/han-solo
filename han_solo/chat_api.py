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


async def api_send(request: Request) -> JSONResponse:
    user = get_current_user()
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    _push(user.name, message, "user")

    try:
        response_text = await letta.send_chat_message(message, user.name)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    if response_text:
        _push("Ren", response_text, "assistant")

    return JSONResponse({"response": response_text})


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
