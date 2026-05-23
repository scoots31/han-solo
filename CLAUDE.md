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
- `han_solo/app_html.py` — Render-hosted web UI (Chat, Memory, Workspace, Frameworks). Served at han-solo-mcp.onrender.com.
- `han_solo/server.py` — FastMCP server, API routes
- `han_solo/tools/` — MCP tool implementations

**Cloudflare Pages (deploy manually)**
The docs site and workspace UI. Code lives in `docs/`. Deploy command:
```
cd ~/Developer/han-solo/docs && zsh -l -c "wrangler pages deploy . --project-name han-solo-docs"
```
- `docs/workspace.html` — **The live workspace app** (sidebar with Ren, Session, Workspace, Frameworks, Development). Served at han-solo-docs.pages.dev/workspace.html. **Edit this for sidebar nav changes.**
- `docs/index.html` — Han Solo docs home page (han-solo-docs.pages.dev)
- `docs/framework/` — Framework guide docs (getting-started, phase guides, reference)
- `docs/logbook.html`, `docs/transcripts.html`, `docs/dashboard.html` — Operational docs pages
- `docs/roadmap.html` — Roadmap page (accessible via Han Solo Overview in Development nav)

**When you don't know which file to edit — ask:** is this the workspace sidebar/UI (→ `docs/workspace.html`) or the Render app UI (→ `han_solo/app_html.py`) or a docs page (→ `docs/*.html`)?

## Docs preview server

```
python3 -m http.server 7700 --directory /Users/scottheinemeier/Developer/han-solo/docs
```

## Key paths

- Approved design reference: `docs/design/han-solo-design.html`
- Shared CSS: `docs/framework/_shared.css`
- Framework docs: `docs/framework/` (18+ pages)
- System state reference: `docs/system-state.md` (source of truth for Letta project_state block)
