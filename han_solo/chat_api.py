"""
Chat API — REST endpoints backing the Han Solo web UI.

In-memory message history: cleared on deploy. Acceptable for v1.
"""
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from .auth import get_current_user
from . import letta_client as letta
from .chat_html import CHAT_HTML

# ---------------------------------------------------------------------------
# In-memory message history (shared across all users, max 200 messages)
# ---------------------------------------------------------------------------

_history: list[dict] = []


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
