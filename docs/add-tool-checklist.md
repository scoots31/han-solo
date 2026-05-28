# Adding a Tool to Han Solo — Complete Checklist

Every tool has two independent surfaces: the **MCP server** (what Claude Code calls) and
**Ren's Letta agent** (what Ren calls from chat). They don't share registration — you must
update both. Missing either surface is the most common failure mode.

---

## Step 1 — Write the tool function

In `han_solo/tools/<file>.py`, add an `@server.tool()` decorated async function inside
the `register(server)` function. Match the docstring pattern of existing tools — Letta and
Claude Code both read it to understand when to call the tool.

If the tool needs DB operations, add the corresponding `async def` to `han_solo/db.py` first.

## Step 2 — Confirm the tools file is registered

In `han_solo/server.py`, check two things:
- The tools file is imported at the top (line ~30): `from .tools import ..., <file>`
- `<file>.register(server)` is called in the register block (line ~51)

If the file is already registered (e.g. you added a tool to an existing file), no change needed.

## Step 3 — Add an API route (if the tool needs a UI endpoint)

If the tool's action should also be triggerable from the workspace UI (not just from chat
or Claude Code), add:
- An `async def api_<action>` handler in `han_solo/server.py`
- A `Route(...)` entry in the routes list at the bottom of `server.py`

Not every tool needs this — read-only or chat-only tools skip this step.

## Step 4 — Update the UI (if Step 3 added a route)

Add the corresponding button, function, and fetch call in `han_solo/app_html.py`.
Add CSS for any new states or button variants.

## Step 5 — Add to Ren's canonical tool set (if Ren should have access)

In `han_solo/letta_client.py`, add the tool name to `CANONICAL_REN_TOOL_NAMES`.

`ensure_ren_tools()` runs at every server startup and syncs Ren's tool list to exactly
this set — tools in the set but not yet in Letta's registry are silently skipped until
they appear (after the next deploy and MCP reconnect).

**Do not add tools that would create circular dependencies** — any tool that calls back
into Letta while Letta is waiting for an MCP response will hang indefinitely.

## Step 6 — Update verify.py

In `scripts/verify.py`, update `EXPECTED_HAN_SOLO_TOOLS` to include the new tool name.
If the tool is destructive or a write operation, also add it to `ALLOWED_WRITE_TOOLS_ON_REN`.

This is the regression guard — if verify.py isn't updated, the next regression run will
flag the tool as unexpected and fail the check.

## Step 7 — Commit and push

Commit all changed files together. The commit triggers a Render deploy.

On Render deploy:
- The new tool appears in the MCP server's `tools/list` endpoint immediately
- Letta reconnects to the MCP server and discovers new tools (may take a few minutes)
- `ensure_ren_tools()` fires at startup and attaches everything in the canonical set

## Step 8 — Test in a new Claude Code session

**MCP tools are registered at session start.** New tools added in the current session
will NOT appear as callable tools until the next Claude Code session. Open a fresh session
to test any new MCP tool.

For Ren's Letta tools: test by sending her a message that should trigger the new tool.
If the tool doesn't appear, check the Render deploy logs and call `ensure_ren_tools`
manually via the admin endpoint or a server restart.

---

## Quick reference — files touched per tool type

| What you're adding | Files changed |
|---|---|
| MCP-only tool (Claude Code calls, not Ren) | `tools/<file>.py`, `db.py` (if DB needed) |
| Ren tool (chat-accessible) | Above + `letta_client.py`, `verify.py` |
| Tool with UI endpoint | Above + `server.py` (route + handler), `app_html.py` |
| Tool with DB operations | Above + `db.py` |

---

## The failure pattern we hit (2026-05-27)

`create_notecard` and `update_notecard` existed in the MCP server for weeks but were never
added to `CANONICAL_REN_TOOL_NAMES`. Ren could see them in her tool list only if manually
attached — they'd vanish on the next model switch or server restart because `ensure_ren_tools()`
would sync back to the canonical set and drop them. This checklist was written immediately
after closing this gap.
