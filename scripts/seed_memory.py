"""
seed_memory.py — Seed Ren's archival memory with project context, ren-memory files,
and selected MemPalace drawers.

Run from the han-solo repo root:
    python3 scripts/seed_memory.py

Requires: pip install requests
Skips passages already inserted (tracks by tag in a local .seeded file).
Pauses 3s between inserts to avoid Voyage AI rate limiting.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

LETTA_URL     = "https://han-solo-letta.onrender.com"
LETTA_API_KEY = "KTZbsSbNocYbp7a-qhk87RwboYiLcX_W"
AGENT_ID      = "agent-44d4a28a-9d66-4aea-b327-2f77b23359ef"
SEEDED_FILE   = os.path.join(os.path.dirname(__file__), ".seeded_passages")

# ---------------------------------------------------------------------------
# HTTP helper — follows Render's http:// redirects with auth preserved
# ---------------------------------------------------------------------------

def letta_request(method, path, body=None, timeout=120):
    url = f"{LETTA_URL}{path}"
    data = json.dumps(body).encode() if body else None
    for attempt in range(2):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {LETTA_API_KEY}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 307, 308) and attempt == 0:
                location = e.headers.get("Location", "")
                location = location.replace("http://", "https://", 1)
                url = location
                continue
            body_text = e.read().decode()[:200]
            print(f"  HTTP {e.code}: {body_text}")
            raise
    raise RuntimeError(f"Too many redirects for {path}")


# ---------------------------------------------------------------------------
# Passage insertion
# ---------------------------------------------------------------------------

def load_seeded():
    if not os.path.exists(SEEDED_FILE):
        return set()
    with open(SEEDED_FILE) as f:
        return set(line.strip() for line in f if line.strip())


def mark_seeded(key):
    with open(SEEDED_FILE, "a") as f:
        f.write(key + "\n")


def insert_passage(content, tags, key, seeded):
    if key in seeded:
        print(f"  skip (already seeded): {key}")
        return False
    if not content or not content.strip():
        print(f"  skip (empty): {key}")
        return False
    try:
        letta_request("POST", f"/v1/agents/{AGENT_ID}/archival-memory", body={
            "text": content.strip(),
        })
        mark_seeded(key)
        print(f"  ✓ {key}")
        time.sleep(3)
        return True
    except Exception as e:
        print(f"  ✗ {key}: {e}")
        time.sleep(5)
        return False


# ---------------------------------------------------------------------------
# Content sources
# ---------------------------------------------------------------------------

def chunk_markdown(text, max_chars=2000):
    """Split markdown by ## headers into chunks, keeping each under max_chars."""
    chunks = []
    current = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        if line.startswith("## ") and current and current_len > 200:
            chunks.append("".join(current).strip())
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)
            if current_len > max_chars:
                chunks.append("".join(current).strip())
                current = []
                current_len = 0

    if current:
        chunks.append("".join(current).strip())

    return [c for c in chunks if len(c.strip()) > 100]


def read_file(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception as e:
        print(f"  Could not read {path}: {e}")
        return ""


# ---------------------------------------------------------------------------
# Project summaries (synthesized from handoffs — read 2026-05-12)
# ---------------------------------------------------------------------------

PROJECT_SUMMARIES = [
    {
        "key": "project_summary_solo_companion",
        "tags": ["project", "solo-companion", "summary"],
        "content": """PROJECT: Solo Companion — Framework Build Tracker

Solo Companion is a local Mac web app (port 8710) that tracks software build projects managed through the Solo Builder Framework. Built by Scott and Ren across 6 phases and 37 slices — all complete as of 2026-05-05.

Features: Sidebar with project list, Dashboard (Needs Attention, three-bucket status view), Project Detail (5 tabs: Overview, Slices, Deliverables, Review, Activity), Review Flow, Activity Feed, and Board View (kanban by deliverable, all-projects default). Syncs to a Cloudflare cloud viewer (scoots31/solo-companion, private).

Stack: Python stdlib only, Flask-like local server, SQLite, dark theme (#090806 / #EDE8E0 / #E8971C). Cloud viewer is a Cloudflare Worker SPA.

Current state: No active build phase. All 37 slices Done. Next cycle TBD. Fantasy player-evaluation project is excluded from companion (legacy backlog format, is_active=0 in SQLite).

Open: Phase 5 has not had a formal solo-qa pass. Player-evaluation migration to records-spec format would allow it to sync — migration cost not yet assessed.""",
    },
    {
        "key": "project_summary_fantasy_football",
        "tags": ["project", "fantasy-football", "summary"],
        "content": """PROJECT: Fantasy Player Evaluation System — Dynasty Fantasy Football Tool

Live at https://fantasy-player-evaluation-system-production.up.railway.app. Scott's dynasty fantasy football grading and analysis system. 612 players graded. Built with FastAPI + PostgreSQL on Railway.

Features: Home page (Power Rankings, Top 5 by Position), Player Evaluation (search, detail card, lens strip, bucket panel, PFF stats, contracts), Roster View, League View, Trade Evaluator (two-card UI, proposal cards, verdict bar), Weekly Results, Matchup Analysis, Rookies (2026 class, grades, ADP, depth charts), Draft Room (4 tabs), Q&A, Settings.

Data sources: MFL is the only scoring source. nflverse for schedule only. PFF stats uploaded via Settings. Contracts sync blocked — nfl_data_py not compatible with Python 3.13.

Deploy: pg_dump from local → pg_restore to Railway. NEVER re-sync from APIs when a working local DB exists. Procfile: uvicorn app.main:app. Grade season (2026) ≠ MFL season (2025).

Open items: is_scott flag not set (all franchises have is_scott=False — need to identify Scott's franchise ID), PFF upload pending, contracts sync blocked on nfl_data_py py313.

★★★★★ Scott: "almost a decade in the making — excel → tableau → this. A dream come true." (2026-05-10)""",
    },
    {
        "key": "project_summary_garden_planner",
        "tags": ["project", "garden-planner", "summary"],
        "content": """PROJECT: Garden Planner — Personal Gardening App for Scott and his wife

Framework-managed project. Deployed to Cloudflare Pages (frontend) + Railway (backend + PostgreSQL) + Cloudflare R2 (images). github.com/scoots31/garden-planner.

Features: Plant library (113 plants), location-aware planting calendar with frost date offsets, zone-neutral growing data, garden journal (Phase 5, not started). Authentication required for calendar and detail views; library is public for guest browsing (12 curated plants + sign-up banner).

Phase status: Phase 1 Foundation ✓, Phase 2 Plant Data ✓, Phase 3 Calendar Engine ✓, Phase 4 Library + Calendar UI (In Progress — Images Pending), Phase 5 Journal (Not started).

Blocker: 52 plants still have external iNaturalist image URLs instead of R2-hosted photos. 61 plants already have verified R2 photos. Scott is sourcing the remaining 52 photos. Phase 4 cannot be accepted until all 113 plants have R2 images. Use upload_local_images.py to upload batches.

Key data model: days_to_maturity (min), days_to_maturity_max (max, nullable), indoor_weeks_before_frost (null for direct sow), cold_tolerant + cold_tolerance_weeks for direct-sow timing. Security class: Multi-tenant · Authentication · Personal.""",
    },
    {
        "key": "project_summary_chase_the_light_swiftui",
        "tags": ["project", "chase-the-light", "ios", "summary"],
        "content": """PROJECT: Chase the Light — iOS Photography Trip Planner (SwiftUI Product)

Framework-managed SwiftUI product. Phase 1 complete: 6-step planning flow, per-day departure time (D-01), skeleton redesign. All Phase 1 slices Done, D-01 Accepted.

The app helps photographers plan multi-day shooting trips — locations, travel chain, light timing, gas stops. Core planning chain: start_location and final_location are the only authoritative location fields per day. build_location_chain() must be called after any final_location change.

Current state: At Phase 1 close-out threshold. Next: run Phase Test to formally close Phase 1, or scope Phase 2 features and open new phase.

Open questions (unresolved): auth strategy, backend timing for live data, community library seeding model.

Separate from the local CTL app (~/Apps port 8701/8702) — that is a Python stdlib local tool for Scott's personal use. The SwiftUI product is a separate greenfield build, never mixing Track 1 (local) and Track 2 (product) code.""",
    },
    {
        "key": "project_summary_local_apps",
        "tags": ["project", "local-apps", "summary"],
        "content": """PROJECT: Local Mac App Suite (~/Apps)

Four local web apps running on Scott's Mac. Python stdlib only — no external packages, no build step. Auto-started via LaunchAgent at login.

| App | Port | Purpose |
| Launcher | 8700 | App portal and navigation hub |
| CTL Library | 8701 | Chase the Light location library |
| CTL Trips | 8702 | Photography trip planner with Google Maps integration |
| Weekly Budget | 8765 | Personal finance tracker |

Dark theme throughout: --bg:#090806 --text:#EDE8E0 --gold:#E8971C. Font: Space Grotesk.

Data: ~/Apps/data/ (gitignored). Google Maps API key in ~/Apps/data/chase_the_light/config.json — never hardcoded or committed.

CTL planning chain is non-negotiable: start_location and final_location are the authoritative fields per day. build_location_chain() must run after any final_location change. Gas stops use the day-scoped city index, not the full trip index.

Python: /opt/homebrew/bin/python3 (3.13.13). Venv at ~/Apps/.venv for any framework tools.""",
    },
    {
        "key": "project_summary_han_solo",
        "tags": ["project", "han-solo", "summary"],
        "content": """PROJECT: Han Solo — Framework as Owned Application

Han Solo is the project to build the Solo Builder Framework into a real product — a private multi-user AI workspace for Scott and Ted, with Ren as a persistent AI partner with genuine long-term memory.

Infrastructure (all live as of 2026-05-12):
- han-solo-db: PostgreSQL 16 + pgvector on Render ($7/mo)
- han-solo-letta: Letta v0.16.7 at han-solo-letta.onrender.com ($7/mo)
- han-solo-mcp: MCP server at han-solo-mcp.onrender.com, 15 tools ($7/mo)
- Chat UI: live at han-solo-mcp.onrender.com/ — group chat, Ren gold / Scott blue / Ted green identity, memory panel, light/dark mode
- Ren agent: ren-v1 (agent-44d4a28a-9d66-4aea-b327-2f77b23359ef), Letta MemGPT agent with Voyage-3 embeddings and Claude Sonnet 4.6 as the LLM

Design sessions completed: Session 1 (module inventory), Session 2 (application architecture), Session 3 (interface design). Session 4 (collaboration model) deferred until v1 core is running.

Pending: session brief (nightly sleeptime job), private messaging (@mention and private thread), full memory seeding (ren-memory + MemPalace migration), Ted conversation (notes layer schema), notes layer build.

Private to Scott and Ted only. Codebase: scoots31/han-solo (private). Deployment: ~/Developer/han-solo/DEPLOYMENT.md — 16 challenges logged.""",
    },
    {
        "key": "project_summary_sbf_framework",
        "tags": ["project", "framework", "sbf", "summary"],
        "content": """PROJECT: Solo Builder Framework (SBF) — Engineering Playbook

The Solo Builder Framework is the full methodology Scott and Ren have built for shipping software products as a solo founder with AI. Lives at ~/Developer/engineering-playbook (private, local-only, not on GitHub).

Framework version: v2.7.0. Phases: Start → Brainstorm → Discover → Tech Context → Design Sprint → Data Scaffold → Design Review → PRD to Plan → To Issues → Solo Build → Solo QA → Phase Test → Deploy. Supporting skills: research-spike, grill-me, to-prd, principal-engineer, agent-room, tdd, frontend-design, qa-triage, onboard. Workshop: scope-check, spike, land. Companion: nivya (recall-only). Testing: solo-simulator. Framework partner: Ren.

Key principles: process-first (to-be map is the contract), four anchors (design + data + done + process), phase gates (explicit named confirmation), always-on skills (process-mapper, product-continuity, framework-health, retrospective), quality contract (4 categories per slice + Check 9 security baseline), verbatim quote at solo-build Step 0.

Docs deployed to Cloudflare Pages: sbf-framework-docs.pages.dev. Comms cascade sub-agent handles all doc updates + deploy in one pass.

Open framework gaps: parallel pipeline skill design (logged in shared/ideas.md), discovery gate for data-heavy products (exact records list as discovery output), prd-to-plan fold.""",
    },
]


# ---------------------------------------------------------------------------
# ren-memory files
# ---------------------------------------------------------------------------

REN_MEMORY_FILES = [
    {
        "path": "/Users/scottheinemeier/Developer/ren-memory/context.md",
        "tags": ["ren-memory", "context", "session-history"],
        "key_prefix": "ren_memory_context",
    },
    {
        "path": "/Users/scottheinemeier/Developer/ren-memory/curator-summary.md",
        "tags": ["ren-memory", "framework", "curator"],
        "key_prefix": "ren_memory_curator",
    },
    {
        "path": "/Users/scottheinemeier/Developer/ren-memory/han-solo.md",
        "tags": ["ren-memory", "han-solo", "design"],
        "key_prefix": "ren_memory_han_solo",
    },
    {
        "path": "/Users/scottheinemeier/Developer/ren-memory/pending.md",
        "tags": ["ren-memory", "pending", "backlog"],
        "key_prefix": "ren_memory_pending",
    },
    {
        "path": "/Users/scottheinemeier/Developer/ren-memory/brainstorm-data-config-module-2026-05-04.md",
        "tags": ["ren-memory", "brainstorm", "data-config"],
        "key_prefix": "ren_memory_data_config",
    },
]


# ---------------------------------------------------------------------------
# MemPalace drawers via direct ChromaDB SQLite access
# ---------------------------------------------------------------------------

CHROMA_DB = "/Users/scottheinemeier/.mempalace/palace/chroma.sqlite3"


def fetch_mempalace_wing(wing):
    """Return list of (id, room, document_text) for all drawers in a wing."""
    import sqlite3
    conn = sqlite3.connect(CHROMA_DB)
    try:
        # Get all embedding IDs for this wing
        ids = conn.execute("""
            SELECT DISTINCT e.id
            FROM embeddings e
            JOIN embedding_metadata em ON e.id = em.id
            WHERE em.key = 'wing' AND em.string_value = ?
        """, (wing,)).fetchall()

        results = []
        for (eid,) in ids:
            # Get document text
            doc_row = conn.execute("""
                SELECT string_value FROM embedding_metadata
                WHERE id = ? AND key = 'chroma:document'
            """, (eid,)).fetchone()
            if not doc_row:
                continue
            doc = doc_row[0]

            # Get room
            room_row = conn.execute("""
                SELECT string_value FROM embedding_metadata
                WHERE id = ? AND key = 'room'
            """, (eid,)).fetchone()
            room = room_row[0] if room_row else ""

            results.append((str(eid), room, doc))
        return results
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Ren Memory Seeder ===\n")
    seeded = load_seeded()
    print(f"Already seeded: {len(seeded)} passages\n")

    inserted = 0
    skipped = 0

    # ── 1. Project summaries ─────────────────────────────────────────────────
    print("── Project summaries ──")
    for s in PROJECT_SUMMARIES:
        result = insert_passage(s["content"], s["tags"], s["key"], seeded)
        if result:
            inserted += 1
        else:
            skipped += 1

    # ── 2. ren-memory files ──────────────────────────────────────────────────
    print("\n── ren-memory files ──")
    for f in REN_MEMORY_FILES:
        text = read_file(f["path"])
        if not text:
            continue
        chunks = chunk_markdown(text)
        print(f"  {os.path.basename(f['path'])}: {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            key = f"{f['key_prefix']}_{i:02d}"
            result = insert_passage(chunk, f["tags"], key, seeded)
            if result:
                inserted += 1
            else:
                skipped += 1

    # ── 3. MemPalace wing_ren ────────────────────────────────────────────────
    print("\n── MemPalace: wing_ren ──")
    _seed_mempalace_wing("wing_ren", ["mempalace", "ren", "relationship"], seeded)

    # ── 4. MemPalace projects ────────────────────────────────────────────────
    print("\n── MemPalace: projects ──")
    _seed_mempalace_wing("projects", ["mempalace", "projects"], seeded)

    print(f"\n=== Done. Inserted: {inserted}  Skipped: {skipped} ===")


def _seed_mempalace_wing(wing, base_tags, seeded):
    drawers = fetch_mempalace_wing(wing)
    print(f"  Found {len(drawers)} drawers in {wing}")
    for (eid, room, doc) in drawers:
        key  = f"mempalace_{wing}_{eid}"
        tags = base_tags + ([room] if room else [])
        text = f"[MemPalace · {wing} · {room}]\n\n{doc}" if room else f"[MemPalace · {wing}]\n\n{doc}"
        insert_passage(text, tags, key, seeded)


if __name__ == "__main__":
    main()
