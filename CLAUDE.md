# han-solo — Ren's persistent cloud environment

## Absolute rules

**Commit message standard**
Every commit must include two things, written by Claude at the time of the commit — not reconstructed afterward:
1. What changed — one sentence describing the specific change
2. Why it was made — one sentence on the reason, decision, or problem it solves
Thin messages ("updated db.py", "fixed bug") are not acceptable. The why must be explicit.

**No agents. No worktrees. Ever.**
Never use the Agent tool. Never use EnterWorktree. Never pass `isolation: "worktree"` to any call.
All work happens directly in the current conversation. No exceptions for any reason — not complexity,
not parallelism, not isolation. This rule has been violated multiple times in han-solo sessions.
Each violation caused hours of rework, design drift, and session context loss.

**No batching visual/design changes without approval.**
One change at a time. Scott reviews and approves before anything moves forward.

## Two separate deployments — know which one you're touching

**Render (auto-deploys on git push)**
The live MCP server and Render-hosted app. Code lives in `han_solo/`.
- `han_solo/server.py` — FastMCP server, API routes
- `han_solo/tools/` — MCP tool implementations
- `han_solo/app_html.py` — **LEGACY `/chat` endpoint only. DO NOT edit for any UI change.** See `docs/workspace.html` instead.

**⚠️ UI source of truth: `docs/workspace.html`**
All workspace UI changes (nav, screens, layout, links) go in `docs/workspace.html`. This file is served by BOTH Render (at `/workspace`) AND Cloudflare Pages. Git push updates Render. Wrangler deploy updates Cloudflare.

**Cloudflare Pages (deploy manually)**
The docs site. Code lives in `docs/`. Deploy command:
```
wrangler pages deploy docs --project-name sbf-framework-docs
```
- `docs/workspace.html` — **The live workspace app.** Edit for ALL UI changes. Served at both han-solo-mcp.onrender.com/workspace AND sbf-framework-docs.pages.dev.
- `docs/index.html` — Han Solo docs home page
- `docs/framework/` — Framework guide docs (getting-started, phase guides, reference)
- `docs/logbook.html`, `docs/transcripts.html`, `docs/dashboard.html` — Operational docs pages
- `docs/roadmap.html` — Roadmap page (accessible via Han Solo Overview in Development nav)

**When you don't know which file to edit — stop and check the component map below before touching anything.**

## Component map (use numbers in conversation)

| # | Name | Edit here | Deploy |
|---|------|-----------|--------|
| 1 | Workspace UI — **ALL UI changes go here** | `docs/workspace.html` | git push (Render) + wrangler (Cloudflare) |
| 2 | Han Solo Docs (overview, operational pages) | `docs/*.html` | wrangler → han-solo-docs |
| 3 | Framework Docs (guides, skills reference, decks) | `docs/framework/*.html` | wrangler → han-solo-docs |
| 4 | MCP Server (FastMCP bridge, API, tools) | `han_solo/server.py`, `han_solo/tools/` | git push → auto |
| 5 | Letta (Ren's memory, v0.16.8) | Via MCP tools | Render managed |
| 6 | Database (PostgreSQL — T4, skills, transcripts) | Via API or scripts | Render managed |
| 7 | Legacy /chat endpoint (read-only — not the workspace) | `han_solo/app_html.py` | do not edit |
| 8 | Claude Code (local execution, MCP client) | Claude Code settings, hooks, skills | — |
| 9 | Framework Vers1 (phase skills source of truth) | `~/Developer/Framework Vers1/skills/` | write_skill MCP → #6 |
| 10 | verify.py (57-check health monitor) | `scripts/verify.py` | LaunchAgent, 30 min |
| 11 | Transcript Parser (JSONL → DB) | `scripts/parse_transcripts.py` | LaunchAgent, 30 min |
| 12 | ren-local (local session log) | `~/Developer/ren-local/` | — |
| 13 | GitHub repo (scoots31/han-solo) | git push | Auto #4 #7, manual #1 #2 #3 |

Visual version: `docs/map.html` (han-solo-docs.pages.dev/map.html)

## Docs preview server

```
python3 -m http.server 7700 --directory /Users/scottheinemeier/Developer/han-solo/docs
```

## Key paths

- Approved design reference: `docs/design/han-solo-design.html`
- Shared CSS: `docs/framework/_shared.css`
- Framework docs: `docs/framework/` (18+ pages)
- System state reference: `docs/system-state.md` (source of truth for Letta project_state block)
