"""
Han Solo MCP Server — entry point.

Formal boundary between Claude (any tool, anywhere) and Han Solo's memory layer.
All reads and writes go through here. Claude never touches Letta directly.

Transport: Streamable HTTP (stateless) — endpoint at /mcp
Auth:      Bearer token per user, validated on every request
Deploy:    Render web service
"""
import contextlib
import logging

import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from .auth import BearerAuthMiddleware, get_current_user
from .config import REN_AGENT_NAME, REN_AGENT_ID
from . import letta_client as letta
from . import db
from .tools import memory, signals, phase, brief, portraits, notecards, t4
from . import chat_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP server — register all tool groups
# ---------------------------------------------------------------------------

# Disable built-in DNS rebinding protection — we enforce security via bearer token auth.
# Without this, FastMCP rejects requests from the Render hostname with 421.
_transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

server = FastMCP("han-solo", transport_security=_transport_security)

memory.register(server)
signals.register(server)
phase.register(server)
brief.register(server)
portraits.register(server)
notecards.register(server)
t4.register(server)


# ---------------------------------------------------------------------------
# Health endpoint — no auth, for Render health check
# ---------------------------------------------------------------------------

async def health(request: Request) -> JSONResponse:
    agent_id = letta._ren_agent_id
    return JSONResponse({
        "status": "ok" if agent_id else "degraded",
        "ren_agent": agent_id or "not_initialised",
    })


# ---------------------------------------------------------------------------
# ASGI app
#
# FastMCP's streamable_http_app() creates a Starlette app with its own lifespan
# that initialises the SSE session manager's task group (required for streaming).
# We need BOTH lifespans to run — FastMCP's and ours (httpx client + Letta agent).
#
# Strategy:
#   1. Call streamable_http_app() to trigger lazy session manager creation.
#   2. Add the /health route directly to that Starlette app's router.
#   3. Replace the router's lifespan with a combined one that runs both.
#   4. Wrap with our raw ASGI auth middleware (avoids BaseHTTPMiddleware SSE breakage).
# ---------------------------------------------------------------------------

# Step 1 — get FastMCP's Starlette app (creates session_manager lazily)
_mcp_app = server.streamable_http_app()

# Step 2 — inject custom routes before the /mcp route
async def admin_agent_info(request: Request) -> JSONResponse:
    agent_id = await letta.ensure_ren_agent_id()
    resp = await letta._letta("GET", f"{letta.LETTA_URL}/v1/agents/{agent_id}/")
    data = resp.json()
    return JSONResponse({
        "agent_id": agent_id,
        "name": data.get("name"),
        "llm_config": data.get("llm_config"),
    })


async def admin_patch_model(request: Request) -> JSONResponse:
    body = await request.json()
    model = body.get("model", "").strip()
    if not model:
        return JSONResponse({"error": "model required"}, status_code=400)
    result = await letta.patch_agent_model(model)
    return JSONResponse({"patched": True, "llm_config": result.get("llm_config")})


async def api_write_core_block(request: Request) -> JSONResponse:
    """REST endpoint for synthesis script to update a core memory block."""
    body = await request.json()
    label = body.get("label", "").strip()
    value = body.get("value", "")
    if not label:
        return JSONResponse({"error": "label required"}, status_code=400)
    try:
        result = await letta.write_core_block(label, value)
        return JSONResponse({"written": True, "label": label})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


async def api_list_signals(request: Request) -> JSONResponse:
    """GET /api/signals?type=texture|directional|relational"""
    get_current_user()
    signal_type = request.query_params.get("type", "").strip() or None
    signals = await db.list_signals(signal_type=signal_type)
    return JSONResponse([
        {
            "id": s["id"],
            "signal_type": s["signal_type"],
            "subject": s["subject"],
            "content": s["content"],
            "session_date": s["session_date"].isoformat() if s.get("session_date") else None,
            "author": s["author"],
            "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
        }
        for s in signals
    ])


async def api_write_signal_rest(request: Request) -> JSONResponse:
    """REST endpoint for synthesis script to write an archival signal."""
    from datetime import date as _date
    body = await request.json()
    signal_type = body.get("signal_type", "").strip()
    subject = body.get("subject", "").strip()
    content = body.get("content", "").strip()
    session_date = body.get("session_date", "") or _date.today().isoformat()

    if not all([signal_type, subject, content]):
        return JSONResponse({"error": "signal_type, subject, content required"}, status_code=400)

    valid_types = {"relational", "directional", "ren", "texture"}
    valid_subjects = {"scott", "ted", "ren", "project", "framework"}
    if signal_type not in valid_types or subject not in valid_subjects:
        return JSONResponse({"error": "invalid signal_type or subject"}, status_code=400)

    try:
        tags = ["signal", signal_type, subject, session_date, "author:synthesis"]
        letta_result = await letta.insert_passage(content=content, tags=tags)
        await db.create_signal(signal_type=signal_type, subject=subject, content=content, session_date=session_date)
        return JSONResponse({"written": True, "id": letta_result.get("id")})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


async def api_list_archival_passages(request: Request) -> JSONResponse:
    """List archival passages for the synthesis cron's T2→T3 promotion pass."""
    limit = int(request.query_params.get("limit", "500"))
    try:
        passages = await letta.list_passages(limit=limit)
        return JSONResponse([
            {
                "id": p.get("id"),
                "text": p.get("text", ""),
                "created_at": p.get("created_at", ""),
            }
            for p in passages
        ])
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


async def api_delete_archival_passage(request: Request) -> JSONResponse:
    """Delete a single archival passage by ID. Used by T2→T3 promotion after rewrite."""
    body = await request.json()
    passage_id = body.get("id", "").strip()
    if not passage_id:
        return JSONResponse({"error": "id required"}, status_code=400)
    try:
        await letta.delete_passage(passage_id)
        return JSONResponse({"deleted": True, "id": passage_id})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


async def api_list_notecards(request: Request) -> JSONResponse:
    """GET /api/notecards?status=active|completed|archived (default: active+completed)"""
    get_current_user()
    status = request.query_params.get("status", "")
    cards = await db.list_notecards(status=status or None)
    return JSONResponse([
        {
            "id": c["id"],
            "text": c["text"],
            "creator": c["creator"],
            "status": c["status"],
            "source": c["source"],
            "session_id": c.get("session_id"),
            "created_at": c["created_at"].isoformat() if c.get("created_at") else None,
        }
        for c in cards
    ])


async def api_create_notecard(request: Request) -> JSONResponse:
    """POST /api/notecards — body: {text, source?}"""
    from . import letta_client as letta_mod
    user = get_current_user()
    body = await request.json()
    text = body.get("text", "").strip()
    source = body.get("source", "manual")
    if not text:
        return JSONResponse({"error": "text required"}, status_code=400)
    session_id = await letta_mod.ensure_ren_agent_id()
    result = await db.create_notecard(text=text, creator=user.id, source=source, session_id=session_id)
    if not result:
        return JSONResponse({"error": "DB write failed"}, status_code=500)
    return JSONResponse({
        "id": result["id"],
        "text": result["text"],
        "creator": result["creator"],
        "status": result["status"],
        "source": result["source"],
        "created_at": result["created_at"].isoformat() if result.get("created_at") else None,
    }, status_code=201)


async def api_update_notecard(request: Request) -> JSONResponse:
    """PATCH /api/notecards/{id} — body: {status: active|completed|archived}"""
    get_current_user()
    try:
        notecard_id = int(request.path_params["notecard_id"])
    except (KeyError, ValueError):
        return JSONResponse({"error": "invalid id"}, status_code=400)
    body = await request.json()
    status = body.get("status", "").strip()
    if status not in {"active", "completed", "archived"}:
        return JSONResponse({"error": "status must be active, completed, or archived"}, status_code=400)
    ok = await db.update_notecard_status(notecard_id, status)
    if not ok:
        return JSONResponse({"error": "not found or DB write failed"}, status_code=404)
    return JSONResponse({"id": notecard_id, "status": status})


async def api_t4_projects(request: Request) -> JSONResponse:
    """GET /api/t4/projects — list projects visible to the caller (owned or shared)."""
    user = get_current_user()
    projects = await db.list_t4_projects()
    projects = [p for p in projects if p["owner"] == user.id or p["visibility"] == "shared"]
    return JSONResponse([
        {
            "project_slug": p["project_slug"],
            "owner": p["owner"],
            "visibility": p["visibility"],
            "current_phase": p["current_phase"],
            "total_slices": p["total_slices"],
            "done_slices": p["done_slices"],
            "total_phases": p["total_phases"],
            "total_deliverables": p["total_deliverables"],
        }
        for p in projects
    ])


async def api_t4_project_patch(request: Request) -> JSONResponse:
    """PATCH /api/t4/projects/{slug} — update visibility (private/shared)."""
    project_slug = request.path_params["project_slug"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    visibility = body.get("visibility", "").strip()
    if visibility not in ("private", "shared"):
        return JSONResponse({"error": "visibility must be 'private' or 'shared'"}, status_code=400)
    ok = await db.update_project_visibility(project_slug, visibility)
    if not ok:
        return JSONResponse({"error": "project not found or update failed"}, status_code=404)
    return JSONResponse({"project_slug": project_slug, "visibility": visibility})


async def api_t4_entries(request: Request) -> JSONResponse:
    """GET /api/t4/{project_slug}/entries?type=slice|deliverable|phase|..."""
    project_slug = request.path_params["project_slug"]
    entry_type = request.query_params.get("type", "").strip()
    if not entry_type:
        return JSONResponse({"error": "type query param required"}, status_code=400)
    rows = await db.list_t4_entries_by_type(project_slug, entry_type)
    return JSONResponse([
        {
            "id": r["id"],
            "entry_type": r["entry_type"],
            "entry_id": r["entry_id"],
            "parent_id": r.get("parent_id"),
            "content": r["content"],
            "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
        }
        for r in rows
    ])


async def api_memory_health(request: Request) -> JSONResponse:
    """Return memory system health: failed transitions + capture stats."""
    failed = await db.get_failed_transitions(hours=24)
    health = db.health_status()
    return JSONResponse({
        "capture": health,
        "failed_transitions_24h": len(failed),
        "failed_transitions": [
            {
                "from_tier": f["from_tier"],
                "to_tier": f["to_tier"],
                "content_key": f["content_key"],
                "error": f["error"],
                "attempted_at": f["attempted_at"].isoformat() if f.get("attempted_at") else None,
            }
            for f in failed
        ],
    })


_docs_dir = os.path.join(os.path.dirname(__file__), "..", "docs")


async def workspace_index(request: Request) -> HTMLResponse:
    with open(os.path.join(_docs_dir, "workspace.html"), "r") as f:
        return HTMLResponse(f.read())


_chat_routes = [
    Mount("/docs", app=StaticFiles(directory=_docs_dir, html=True)),
    Route("/workspace", workspace_index),
    Route("/", workspace_index),
    Route("/chat", chat_api.chat_legacy),
    Route("/api/notecards", api_list_notecards),
    Route("/api/notecards", api_create_notecard, methods=["POST"]),
    Route("/api/notecards/{notecard_id}", api_update_notecard, methods=["PATCH"]),
    Route("/health", health),
    Route("/api/me", chat_api.api_me),
    Route("/api/history", chat_api.api_history),
    Route("/api/send", chat_api.api_send, methods=["POST"]),
    Route("/api/reset-session", chat_api.api_reset_session, methods=["POST"]),
    Route("/api/jobs-status", chat_api.api_jobs_status),
    Route("/api/jobs-paused", chat_api.api_set_jobs_paused, methods=["POST"]),
    Route("/api/memory-panel", chat_api.api_memory_panel),
    Route("/api/memory-health", api_memory_health),
    Route("/api/write-core-block", api_write_core_block, methods=["POST"]),
    Route("/api/t4/projects", api_t4_projects),
    Route("/api/t4/projects/{project_slug}", api_t4_project_patch, methods=["PATCH"]),
    Route("/api/t4/{project_slug}/entries", api_t4_entries),
    Route("/api/signals", api_list_signals),
    Route("/api/write-signal", api_write_signal_rest, methods=["POST"]),
    Route("/api/archival-passages", api_list_archival_passages),
    Route("/api/archival-passage/delete", api_delete_archival_passage, methods=["POST"]),
    Route("/api/admin/agent-info", admin_agent_info),
    Route("/api/admin/patch-model", admin_patch_model, methods=["POST"]),
]
for i, route in enumerate(_chat_routes):
    _mcp_app.router.routes.insert(i, route)


# Step 3 — combined lifespan: our setup + FastMCP's session manager
@contextlib.asynccontextmanager
async def _lifespan(app):
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
        letta.set_client(client)
        try:
            if REN_AGENT_ID:
                logger.info("Using pinned REN_AGENT_ID: %s", REN_AGENT_ID)
                letta.set_ren_agent_id(REN_AGENT_ID)
            else:
                logger.info("Resolving Ren agent '%s'...", REN_AGENT_NAME)
                agent_id = await letta.get_or_create_ren_agent(REN_AGENT_NAME)
                letta.set_ren_agent_id(agent_id)
                logger.info("Ren agent ready: %s", agent_id)
        except Exception as e:
            logger.error("Failed to initialise Ren agent (will retry on next request): %s", e)
        await db.init_pool()
        try:
            async with server.session_manager.run():
                yield
        finally:
            await db.close_pool()


_mcp_app.router.lifespan_context = _lifespan

# Step 4 — raw ASGI auth middleware (preserves SSE streaming)
app = BearerAuthMiddleware(_mcp_app)
