# Claude Plus Deployment Baseline

Captured before adding the `get_claude_plus_blocks` MCP tool.
Baseline date: 2026-05-29

---

## Git State

**han-solo HEAD:** `d42ce78a4a23ec76d12283e55fcf33eedeaa335b`
Commit: Add seed-claude-plus admin endpoint and seed script

---

## Current Letta Tool Registry (agent_tools — what Ren can actually call)

20 tools registered to Ren (agent-fe4a3d5b-bb51-458e-92f1-6a1ee5b0ce94):

1. update_notecard
2. read_core_memory
3. append_t4_entry
4. write_skill
5. get_skill
6. search_transcripts
7. search_t4
8. write_t4_entry
9. list_notecards
10. check_system_health
11. write_core_memory
12. create_notecard
13. delete_notecard
14. list_skills
15. search_code
16. send_message
17. delete_archival_passage
18. get_t4_entry
19. update_open_threads
20. archival_memory_search

---

## server.py Registration Section

```python
from .tools import memory, signals, phase, brief, portraits, notecards, t4, skills, logbook, transcripts, bridge, codebase, health

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
bridge.register(server)
codebase.register(server)
health.register(server)
```

13 tool files, all imported and registered. Order is load-bearing.

---

## han_solo/tools/ File Inventory

| File | register() present |
|---|---|
| bridge.py | yes |
| brief.py | yes |
| codebase.py | yes |
| health.py | yes |
| logbook.py | yes |
| memory.py | yes |
| notecards.py | yes |
| phase.py | yes |
| portraits.py | yes |
| signals.py | yes |
| skills.py | yes |
| t4.py | yes |
| transcripts.py | yes |
| __init__.py | no (empty init) |

All active tool files use the `register(server: FastMCP)` pattern. No dead files, no old `_tool_manager` pattern.

---

## What Changes With the New Tool

Adding: `han_solo/tools/claude_plus.py` — one tool: `get_claude_plus_blocks`

After deploy, post-deploy steps required:
1. POST /api/admin/sync-mcp-tools (registers new tool into Letta registry)
2. Verify via /api/admin/agent-info that `get_claude_plus_blocks` appears in `agent_tools`
3. Test via MCP call

Expected result: `agent_tools` count goes from 20 → 21.
