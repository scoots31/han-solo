"""
Han Solo MCP Server — entry point.

Formal boundary between Claude (any tool, anywhere) and Han Solo's memory layer.
All reads and writes go through here. Claude never touches Letta directly.

Transport: Streamable HTTP (stateless) — endpoint at /mcp
Auth:      Bearer token per user, validated on every request
Deploy:    Render web service
"""
import contextlib
import json
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
from .tools import memory, signals, phase, brief, portraits, notecards, t4, skills, logbook, transcripts
from . import chat_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP server — register all tool groups
# ---------------------------------------------------------------------------

# Disable built-in DNS rebinding protection — we enforce security via bearer token auth.
# Without this, FastMCP rejects requests from the Render hostname with 421.
_transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

server = FastMCP("han-solo", transport_security=_transport_security, stateless_http=True)

memory.register(server)
signals.register(server)
phase.register(server)
brief.register(server)
portraits.register(server)
notecards.register(server)
t4.register(server)
skills.register(server)
logbook.register(server)
transcripts.register(server)


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


async def api_create_core_block(request: Request) -> JSONResponse:
    """REST endpoint to create a new core memory block and attach it to the Ren agent."""
    body = await request.json()
    label = body.get("label", "").strip()
    value = body.get("value", "")
    limit = int(body.get("limit", 10000))
    if not label:
        return JSONResponse({"error": "label required"}, status_code=400)
    try:
        result = await letta.create_core_block(label, value, limit)
        return JSONResponse({"created": True, "label": label, "id": result.get("id")})
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


async def api_get_skill(request: Request) -> JSONResponse:
    """GET /api/skills/{phase_slug} — return skill content for a phase."""
    phase_slug = request.path_params["phase_slug"]
    skill = await db.get_skill(phase_slug)
    if not skill:
        return JSONResponse({"error": "skill not found"}, status_code=404)
    return JSONResponse({
        "phase_slug": skill["phase_slug"],
        "layer": skill["layer"],
        "content": skill["content"],
        "updated_at": skill["updated_at"].isoformat() if skill.get("updated_at") else None,
    })




async def api_memory_access_patterns(request: Request) -> JSONResponse:
    """GET /api/memory/access-patterns?days=30
    Returns the MRI: hot passages, cold passages, dry wells, false positives.
    """
    try:
        days = int(request.query_params.get("days", "30"))
    except ValueError:
        days = 30
    patterns = await db.get_memory_access_patterns(days=days)
    return JSONResponse(patterns)




async def api_get_passage_enrichments(request: Request) -> JSONResponse:
    """GET /api/memory/enrichments/{passage_id} — enrichments Ren has added on retrieval."""
    passage_id = request.path_params["passage_id"]
    enrichments = await db.get_passage_enrichments(passage_id)
    return JSONResponse([
        {
            "id": e["id"],
            "context_note": e["context_note"],
            "session_date": e["session_date"].isoformat() if e.get("session_date") else None,
            "created_at": e["created_at"].isoformat() if e.get("created_at") else None,
        }
        for e in enrichments
    ])


async def api_write_passage_enrichment(request: Request) -> JSONResponse:
    """POST /api/memory/enrichments — Ren records context when meaningfully retrieving a passage."""
    body = await request.json()
    passage_id = body.get("passage_id", "").strip()
    context_note = body.get("context_note", "").strip()
    session_date = body.get("session_date", "").strip() or None
    if not passage_id or not context_note:
        return JSONResponse({"error": "passage_id and context_note required"}, status_code=400)
    ok = await db.write_passage_enrichment(passage_id, context_note, session_date)
    if not ok:
        return JSONResponse({"error": "DB write failed"}, status_code=500)
    return JSONResponse({"written": True}, status_code=201)


async def api_list_session_logs(request: Request) -> JSONResponse:
    """GET /api/session-logs — public, no auth required. Supports ?level=major&tag=letta"""
    level = request.query_params.get("level", "").strip() or None
    tag = request.query_params.get("tag", "").strip() or None
    logs = await db.list_session_logs(level=level, tag=tag)
    return JSONResponse([
        {
            "id": r["id"],
            "session_date": r["session_date"].isoformat() if r.get("session_date") else None,
            "summary": r["summary"],
            "decisions": r["decisions"],
            "open_threads": r["open_threads"],
            "commit_refs": r["commit_refs"],
            "tags": r["tags"],
            "level": r["level"],
            "created_by": r["created_by"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in logs
    ])


async def api_create_session_log(request: Request) -> JSONResponse:
    """POST /api/session-logs — auth required. Body: {summary, decisions?, open_threads?, commit_refs?, tags?, level?, session_date?}"""
    get_current_user()
    body = await request.json()
    summary = body.get("summary", "").strip()
    if not summary:
        return JSONResponse({"error": "summary required"}, status_code=400)
    level = body.get("level", "minor").strip()
    if level not in ("major", "minor"):
        return JSONResponse({"error": "level must be 'major' or 'minor'"}, status_code=400)
    result = await db.create_session_log(
        summary=summary,
        decisions=body.get("decisions", ""),
        open_threads=body.get("open_threads", ""),
        commit_refs=body.get("commit_refs", ""),
        tags=body.get("tags", ""),
        level=level,
        created_by=body.get("created_by", "claude_code"),
        session_date=body.get("session_date"),
    )
    if not result:
        return JSONResponse({"error": "DB write failed"}, status_code=500)
    return JSONResponse({"id": result["id"], "level": result["level"]}, status_code=201)


async def api_list_transcripts(request: Request) -> JSONResponse:
    """GET /api/transcripts — public. Supports ?project=Apps&q=keyword"""
    project = request.query_params.get("project", "").strip() or None
    query = request.query_params.get("q", "").strip()
    if query:
        results = await db.search_session_transcripts(query)
        return JSONResponse([
            {
                "session_id": r["session_id"],
                "project": r["project"],
                "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
                "entry_count": r["entry_count"],
                "is_complete": r["is_complete"],
                "preview": r.get("preview", ""),
            }
            for r in results
        ])
    try:
        days = int(request.query_params.get("days", "45"))
    except ValueError:
        days = 45
    logs = await db.list_session_transcripts(project=project, days=days)
    return JSONResponse([
        {
            "session_id": r["session_id"],
            "project": r["project"],
            "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
            "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
            "entry_count": r["entry_count"],
            "is_complete": r["is_complete"],
        }
        for r in logs
    ])


async def api_get_transcript(request: Request) -> JSONResponse:
    """GET /api/transcripts/{session_id} — public, returns full parsed content."""
    session_id = request.path_params["session_id"]
    result = await db.get_session_transcript(session_id)
    if not result:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({
        "session_id": result["session_id"],
        "project": result["project"],
        "started_at": result["started_at"].isoformat() if result.get("started_at") else None,
        "updated_at": result["updated_at"].isoformat() if result.get("updated_at") else None,
        "entry_count": result["entry_count"],
        "is_complete": result["is_complete"],
        "parsed_content": json.loads(result["parsed_content"]) if isinstance(result["parsed_content"], str) else result["parsed_content"],
        "watermark": result["watermark"],
    })


async def api_upsert_transcript(request: Request) -> JSONResponse:
    """POST /api/transcripts — auth required. Upserts a parsed session transcript.
    Accepts gzip Content-Encoding so WAF doesn't block session content."""
    import gzip as _gzip, json as _json
    get_current_user()
    raw = await request.body()
    if request.headers.get("content-encoding", "").lower() == "gzip":
        raw = _gzip.decompress(raw)
    body = _json.loads(raw)
    session_id = body.get("session_id", "").strip()
    if not session_id:
        return JSONResponse({"error": "session_id required"}, status_code=400)
    result = await db.upsert_session_transcript(
        session_id=session_id,
        project=body.get("project", "Apps"),
        started_at=body.get("started_at", "now"),
        entry_count=body.get("entry_count", 0),
        is_complete=body.get("is_complete", False),
        parsed_content=body.get("parsed_content", []),
        parsed_text=body.get("parsed_text", ""),
        watermark=body.get("watermark", 0),
    )
    if not result or "_error" in result:
        err = result.get("_error", "unknown") if result else "no result"
        return JSONResponse({"error": "DB write failed", "detail": err}, status_code=500)
    return JSONResponse({"session_id": result["session_id"], "entry_count": result["entry_count"]}, status_code=200)


async def api_get_latest_verify_run(request: Request) -> JSONResponse:
    """GET /api/verify-runs/latest — public. Returns most recent verify.py result."""
    result = await db.get_latest_verify_run()
    if not result:
        return JSONResponse({"error": "no verify runs found"}, status_code=404)
    return JSONResponse({
        "id": result["id"],
        "ran_at": result["ran_at"].isoformat() if result.get("ran_at") else None,
        "passed": result["passed"],
        "failed": result["failed"],
        "total": result["total"],
        "details": result["details"],
        "cold_starts": result["cold_starts"],
    })


async def api_write_verify_run(request: Request) -> JSONResponse:
    """POST /api/verify-runs — auth required. Stores a verify.py run result."""
    get_current_user()
    body = await request.json()
    result = await db.write_verify_run(
        passed=body.get("passed", 0),
        failed=body.get("failed", 0),
        total=body.get("total", 0),
        details=body.get("details", []),
        cold_starts=body.get("cold_starts", []),
    )
    if not result:
        return JSONResponse({"error": "DB write failed"}, status_code=500)
    return JSONResponse({"id": result["id"], "ran_at": result["ran_at"].isoformat()}, status_code=201)


async def api_prune_transcripts(request: Request) -> JSONResponse:
    """POST /api/admin/prune-transcripts — auth required. Deletes sessions older than ?days=45."""
    get_current_user()
    try:
        days = int(request.query_params.get("days", "45"))
    except ValueError:
        days = 45
    deleted = await db.prune_old_transcripts(days=days)
    return JSONResponse({"deleted": deleted, "days": days})


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


# Live app UI — edit docs/workspace.html for all UI changes.
async def workspace_index(request: Request) -> HTMLResponse:
    with open(os.path.join(_docs_dir, "workspace.html"), "r") as f:
        return HTMLResponse(
            f.read(),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )


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
    Route("/api/create-core-block", api_create_core_block, methods=["POST"]),
    Route("/api/skills/{phase_slug}", api_get_skill),
    Route("/api/t4/projects", api_t4_projects),
    Route("/api/t4/projects/{project_slug}", api_t4_project_patch, methods=["PATCH"]),
    Route("/api/t4/{project_slug}/entries", api_t4_entries),
    Route("/api/signals", api_list_signals),
    Route("/api/write-signal", api_write_signal_rest, methods=["POST"]),
    Route("/api/archival-passages", api_list_archival_passages),
    Route("/api/archival-passage/delete", api_delete_archival_passage, methods=["POST"]),
    Route("/api/memory/enrichments/{passage_id}", api_get_passage_enrichments),
    Route("/api/memory/enrichments", api_write_passage_enrichment, methods=["POST"]),
    Route("/api/memory/access-patterns", api_memory_access_patterns),
    Route("/api/admin/agent-info", admin_agent_info),
    Route("/api/admin/patch-model", admin_patch_model, methods=["POST"]),
    Route("/api/admin/prune-transcripts", api_prune_transcripts, methods=["POST"]),
    Route("/api/tts", chat_api.api_tts, methods=["POST"]),
    Route("/api/session-logs", api_list_session_logs),
    Route("/api/session-logs", api_create_session_log, methods=["POST"]),
    Route("/api/transcripts", api_list_transcripts),
    Route("/api/transcripts", api_upsert_transcript, methods=["POST"]),
    Route("/api/transcripts/{session_id}", api_get_transcript),
    Route("/api/verify-runs/latest", api_get_latest_verify_run),
    Route("/api/verify-runs", api_write_verify_run, methods=["POST"]),
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
