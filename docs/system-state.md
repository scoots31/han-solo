# System State — Han Solo Operational Reference

**This file is the source of truth for the `project_state` core block in Letta.**
Letta is the runtime copy. This file is git-versioned and recoverable.

Update protocol: edit this file → commit → write to Letta via `write_core_memory` (block_label: `project_state`).
Never write to Letta first.

Last updated: 2026-05-25

---

## Han Solo Infrastructure (Render)

**Services:**

| Service | URL | Notes |
|---|---|---|
| han-solo-letta | han-solo-letta.onrender.com | Letta v0.16.8 (upgraded 2026-05-22 from v0.16.7, security fix: pickle→JSON sandbox transport). Ren agent: ren-v2 (`agent-fe4a3d5b-bb51-458e-92f1-6a1ee5b0ce94`), model: `claude-haiku-4-5-20251001`, context_window: 32,000 tokens. Reverted from Sonnet 4.6 on 2026-05-25 — Sonnet exceeded Render's proxy timeout causing "could not reach Ren" errors in the workspace chat. Streaming required before Sonnet can be used here. |
| han-solo-mcp | han-solo-mcp.onrender.com/mcp | FastMCP bridge, MCP entrypoint for Ren |
| han-solo-db | Internal only | PostgreSQL 16, 5 GB, Oregon region (Render ID: dpg-d81724vavr4c73b5afig-a) |

- GitHub repo: scoots31/han-solo (public — All Rights Reserved)
- GitHub repo: scoots31/claude-hooks (private — Claude Code hook files, git-tracked 2026-05-23)
- Health check: han-solo-mcp.onrender.com/health

**Background jobs (Render):**

| Job | Status | Notes |
|---|---|---|
| dream.py | ACTIVE | Memory consolidation |
| synthesize.py | REMOVED 2026-05-22 | Render cron deleted. Was never functional — signals table always empty. Cost was real; output was not. |

---

## MCP Tools (Claude Code ↔ Han Solo)

Tools live in `han_solo/tools/` and register with the FastMCP server at `han-solo-mcp.onrender.com/mcp`.

| Tool group | File | Key tools |
|---|---|---|
| Memory | memory.py | write_core_memory, read_core_memory, list_core_memory_blocks |
| Signals | signals.py | write_signal, search_signals, add_portrait_signal |
| Brief | brief.py | get_session_brief, write_pending_thoughts, check_memory_health |
| T4 | t4.py | write_t4_entry, get_t4_entry, search_t4, delete_t4_entry |
| Skills | skills.py | get_skill, list_skills, write_skill |
| Notecards | notecards.py | list_notecards, create_notecard, update_notecard |
| Portraits | portraits.py | read_portrait, write_portrait, read_all_portraits |
| Phase | phase.py | advance_phase, check_phase_gate, get_project_state |
| Logbook | logbook.py | write_session_log, write_session_summary |
| Transcripts | transcripts.py | search_transcripts, enrich_passage |
| **Bridge** | **bridge.py** | **send_to_ren** — synchronous Claude Code → Ren bridge. Added 2026-05-24. |

**`send_to_ren`**: Claude Code calls this to reach Ren mid-session. Message lands in Ren's Letta context; response returned synchronously. Does not appear in workspace UI. Used for architecture decisions, assumption audits, and team handoff notes at session close.

Ren's tool set (10 tools on her Letta agent): search_t4, get_t4_entry, search_signals, get_session_brief, list_notecards, get_skill, list_skills, write_skill, write_t4_entry, search_transcripts. Write tools intentionally allowed: write_skill (Ren can update framework skills) and write_t4_entry (Ren can write decisions log as Architecture Owner). `send_to_ren` is for Claude Code only.

---

## Framework Skills

- **Source of truth:** `~/Developer/Framework Vers1/skills/`
- **Canonical update path:** write_skill MCP tool → `PUT /api/skills/{slug}` on han-solo-mcp
- **Bulk fallback:** `~/Developer/han-solo/scripts/seed_skills.py` (reads from Framework Vers1)
- **Common mistake:** engineering-playbook is NOT the skills source. Corrected 2026-05-22.
- **Ren skill:** now exists in Han Solo DB (created 2026-05-23). Framework Vers1 + local `~/.claude/skills/ren/SKILL.md` + Han Solo DB are all in sync. Invocation: ren-local + Han Solo session brief. No ren-memory, no MemPalace, no engineering-playbook.

---

## Local Scripts (`~/Developer/han-solo/scripts/`)

| Script | Purpose | Notes |
|---|---|---|
| verify.py | 62 checks, 12 sections, cold-start detection. Posts results to Han Solo DB. | Runs every 30 min via LaunchAgent |
| parse_transcripts.py | Parses Claude Code JSONL sessions (~/.claude/projects/). Pushes to Han Solo DB. | 45-day rolling window enforced at API level |
| dream.py | Memory consolidation | Also deployed on Render |
| seed_skills.py | Bulk skill seed from Framework Vers1 | Fallback only; write_skill MCP tool is preferred |
| migrate_archival.py | One-time migration utility | Not for regular use |

---

## Local Environment

- Python: `/opt/homebrew/bin/python3` (3.13.13)
- App venv: `~/Apps/.venv` (Flask, SQLAlchemy, gunicorn, psycopg2, python-dotenv)
- `LETTA_API_KEY`: set in `~/.zshenv` (shell access) and in `~/Library/LaunchAgents/com.scotth.rendream.plist` EnvironmentVariables section (launchd access, added 2026-05-23). If key is rotated, update both.
- LaunchAgent: `~/Library/LaunchAgents/` — runs parse_transcripts.py + verify.py every 30 min

---

## Han Solo Docs Site

- Local: `~/Developer/han-solo/docs/`
- Deploy: Cloudflare Pages (`wrangler deploy` from han-solo repo)
- Key pages: transcripts.html · dashboard.html · how-it-works.html · memory.html · working-with-ren.html · architecture.html
- Known stale: architecture.html SVG still has synthesize/curator nodes — deferred cleanup

---

## What Triggers an Update to This File

- A Render service is added, modified, or deleted
- A background job is added, removed, or changes behavior
- A local script is added, removed, or its purpose changes
- A key path, URL, or environment variable changes
- Something is removed that Ren might still reference

Commit the file, then write the updated content to Letta. Every time.
