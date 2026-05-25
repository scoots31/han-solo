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
from starlette.responses import HTMLResponse, JSONResponse, Response

from .auth import get_current_user
from . import letta_client as letta
from . import db
from .app_html import APP_HTML
from .chat_html import CHAT_HTML
from .config import ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Message history cache — rebuilt from Letta on cold start
# ---------------------------------------------------------------------------

_history: list[dict] = []
_history_loaded: bool = False

# Session length thresholds. Each exchange = 2 entries (user + assistant).
# WARN_AT: surface a note in the UI so Scott can choose a clean stopping point.
# HARD_LIMIT_AT: safety rollover to prevent Letta context crashes.
# NOTE: continuation messages ([[CONTINUES]]) bypass the user-message path, so
# history can grow past WARN_AT without ever hitting the == check. Both limits
# are checked in the continuation path too.
WARN_AT = 60
HARD_LIMIT_AT = 150

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


async def _analyze_image(base64_data: str, media_type: str, user_message: str) -> str:
    """Call Claude directly with a base64 image and return a detailed analysis."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    prompt_text = user_message if user_message else "Describe this image in detail. If there is text, read it. If it is a design, UI, screenshot, or document, describe the content and structure thoroughly."
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64_data}},
        {"type": "text", "text": prompt_text},
    ]
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": "claude-sonnet-4-6", "max_tokens": 1024, "messages": [{"role": "user", "content": content}]},
        )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


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

    # Silent continuation trigger from the UI — Ren picks up where she left off.
    # Bypass message-building and history-push, but still check session limits so
    # continuation loops can't silently blow past WARN_AT and HARD_LIMIT_AT.
    is_continuation = (message == "__continue__")
    if is_continuation:
        cont_history_len = len(_history)
        cont_rolled_over = False
        cont_warning = None

        if cont_history_len >= HARD_LIMIT_AT:
            try:
                current_id = await letta.ensure_ren_agent_id()
                await _flush_capture_buffer(current_id)
                summary = await _synthesize_handoff(_history)
                await letta.reset_conversation(handoff_summary=summary)
                _history = []
                _history_loaded = True
                cont_rolled_over = True
            except Exception:
                pass
        elif WARN_AT <= cont_history_len < HARD_LIMIT_AT:
            cont_warning = "Getting long — good time to start a new session at a natural stopping point."

        session_id = await letta.ensure_ren_agent_id()
        try:
            response_messages, wants_to_continue, usage = await letta.send_chat_message(
                "__system_continue__", "system"
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        asyncio.create_task(db.write_usage_log("chat_ui", **usage))
        for text in response_messages:
            _push("Ren", text, "assistant")
            asyncio.create_task(_capture_message(session_id, "assistant", "Ren", text))
        return JSONResponse({
            "messages": response_messages,
            "response": response_messages[0] if response_messages else "",
            "wants_to_continue": wants_to_continue,
            "session_reset": cont_rolled_over,
            "session_warning": cont_warning,
            "capture_health": db.health_status(),
        })

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
    elif WARN_AT <= history_len < HARD_LIMIT_AT:
        session_warning = "Getting long — good time to start a new session at a natural stopping point."

    # Build the message Ren receives — inline file content or vision analysis when attached
    if attachment and attachment.get("type") == "image":
        name = attachment.get("name", "image")
        data_url = attachment.get("content", "")
        media_type = "image/jpeg"
        b64_data = data_url
        if "," in data_url:
            header, b64_data = data_url.split(",", 1)
            if ":" in header and ";" in header:
                media_type = header.split(":")[1].split(";")[0]
        try:
            analysis = await _analyze_image(b64_data, media_type, message)
            letta_message = f"[Image shared: {name}]\n\nWhat I can see: {analysis}"
            # Write to archival so Ren can search this image later
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            asyncio.create_task(letta.insert_passage(
                f"[image-memory] Scott shared an image on {today}: {name}\n{analysis}",
                ["image-memory", "visual"],
            ))
        except Exception as exc:
            logger.warning("Image analysis failed: %s", exc)
            letta_message = f"[Image: {name} — analysis unavailable]\n{message}" if message else f"[Image: {name} — could not be analyzed]"
        display_text = f"{message}\n\n🖼 {name}" if message else f"🖼 {name}"
    elif attachment:
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
        response_messages, wants_to_continue, usage = await letta.send_chat_message(letta_message, user.name)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    asyncio.create_task(db.write_usage_log("chat_ui", **usage))
    for text in response_messages:
        _push("Ren", text, "assistant")
        asyncio.create_task(_capture_message(session_id, "assistant", "Ren", text))

    return JSONResponse({
        "messages": response_messages,
        "response": response_messages[0] if response_messages else "",  # backwards compat
        "wants_to_continue": wants_to_continue,
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


async def api_tts(request: Request) -> Response:
    """
    Text-to-speech via ElevenLabs.
    POST {"text": "..."} → audio/mpeg binary.
    Used by the chat UI to play Ren's voice — both auto-play and on-demand.
    """
    get_current_user()

    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        return JSONResponse({"error": "TTS not configured"}, status_code=503)

    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "Empty text"}, status_code=400)

    # Truncate very long messages — TTS has a character limit and long passages
    # don't benefit from audio anyway.
    if len(text) > 2000:
        text = text[:2000] + "…"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
                headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
            )
        resp.raise_for_status()
        return Response(content=resp.content, media_type="audio/mpeg")
    except httpx.HTTPStatusError as exc:
        logger.warning("ElevenLabs TTS error %s: %s", exc.response.status_code, exc.response.text)
        return JSONResponse({"error": "TTS request failed"}, status_code=502)
    except Exception as exc:
        logger.warning("TTS unexpected error: %s", exc)
        return JSONResponse({"error": "TTS unavailable"}, status_code=502)
