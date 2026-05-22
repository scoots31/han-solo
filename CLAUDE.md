# han-solo — Ren's persistent cloud environment

## Absolute rules

**No agents. No worktrees. Ever.**
Never use the Agent tool. Never use EnterWorktree. Never pass `isolation: "worktree"` to any call.
All work happens directly in the current conversation. No exceptions for any reason — not complexity,
not parallelism, not isolation. This rule has been violated multiple times in han-solo sessions.
Each violation caused hours of rework, design drift, and session context loss.

**No batching visual/design changes without approval.**
One change at a time. Scott reviews and approves before anything moves forward.

## Stack

- Letta backend (Render) — persistent memory for Ren
- FastMCP bridge (Render) — MCP server at han-solo-mcp.onrender.com/mcp
- 15 MCP tools callable from Claude Code
- Han Solo docs: /Users/scottheinemeier/Developer/han-solo/docs/

## Docs preview server

```
python3 -m http.server 7700 --directory /Users/scottheinemeier/Developer/han-solo/docs
```

## Key paths

- Approved design reference: `docs/design/han-solo-design.html`
- Shared CSS: `docs/framework/_shared.css`
- Framework docs: `docs/framework/` (18+ pages)
