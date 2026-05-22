"""
verify.py — Han Solo system health check.

Verifies the full stack in one pass: tokens, Letta agent, tool counts,
core memory block sizes, T4 access, skills table, MCP server registration.

Run any time you want to confirm the system is intact — especially after
any architecture session that touches tools, memory blocks, or DB schema.

Usage:
    python3 scripts/verify.py

Environment vars required:
    MCP_URL     — Han Solo MCP server URL (default: https://han-solo-mcp.onrender.com)
    MCP_TOKEN   — bearer token (USER_TOKEN_SCOTT or system token)
    LETTA_URL   — Letta server URL (default: https://han-solo-letta.onrender.com)
    LETTA_KEY   — Letta API key
    AGENT_ID    — Ren's agent ID
"""
import json
import os
import sys
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Config — fall back to known values if env not set
# ---------------------------------------------------------------------------

MCP_URL   = os.environ.get("MCP_URL", "https://han-solo-mcp.onrender.com")
MCP_TOKEN = os.environ.get("MCP_TOKEN", "RHcpXjeAJlu_DzhYplsLaUOUSGVrU-gceamJQoXb81Q")
LETTA_URL = os.environ.get("LETTA_URL", "https://han-solo-letta.onrender.com")
LETTA_KEY = os.environ.get("LETTA_API_KEY") or os.environ.get("LETTA_KEY", "")
AGENT_ID  = os.environ.get("AGENT_ID",  "agent-fe4a3d5b-bb51-458e-92f1-6a1ee5b0ce94")

# Expected state — update these when the architecture changes
EXPECTED_HAN_SOLO_TOOLS = {
    "search_t4", "get_t4_entry", "search_signals",
    "get_session_brief", "list_notecards",
    "get_skill", "list_skills",
}
ALWAYS_LOADED_CORE_LIMIT = 10_000
PENDING_THOUGHTS_LIMIT   = 50_000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get(url: str, headers: dict, timeout: int = 20) -> dict | list:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def mcp_get(path: str) -> dict | list:
    return get(f"{MCP_URL}{path}", {"Authorization": f"Bearer {MCP_TOKEN}"})


def letta_get(path: str) -> dict | list:
    return get(f"{LETTA_URL}{path}", {"Authorization": f"Bearer {LETTA_KEY}"})


def mcp_tools_list() -> set[str]:
    """Call MCP tools/list via JSON-RPC and return tool name set."""
    url = f"{MCP_URL}/mcp"
    headers = {
        "Authorization": f"Bearer {MCP_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    data = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 1}).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
    for line in raw.split("\n"):
        if line.startswith("data:"):
            result = json.loads(line[5:])
            return {t["name"] for t in result["result"]["tools"]}
    return set()


PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results = []

def check(label: str, passed: bool, detail: str = "", warn: bool = False) -> bool:
    icon = WARN if (warn and not passed) else (PASS if passed else FAIL)
    line = f"  {icon}  {label}"
    if detail:
        line += f"  —  {detail}"
    results.append((passed or warn, line))
    print(line)
    return passed


# ---------------------------------------------------------------------------
# Run checks
# ---------------------------------------------------------------------------

print(f"\nHan Solo — System Verification")
print(f"{'─' * 50}")

# 1. MCP server health
print("\n[1] MCP server")
try:
    health = mcp_get("/health")
    check("MCP health", health.get("status") == "ok", str(health))
    check("Ren agent ID in health", "ren_agent" in health, health.get("ren_agent", "missing"))
except Exception as e:
    check("MCP reachable", False, str(e))

# 2. Token auth
print("\n[2] Token auth")
try:
    me = mcp_get("/api/me")
    check("Scott token auth", me.get("id") == "scott", f"role={me.get('role')}")
except Exception as e:
    check("Scott token auth", False, str(e))

# 3. MCP tool count
print("\n[3] MCP tools")
try:
    mcp_tools = mcp_tools_list()
    check("MCP exposes tools", len(mcp_tools) >= 25, f"{len(mcp_tools)} tools")
    for name in sorted(EXPECTED_HAN_SOLO_TOOLS):
        check(f"  tool: {name}", name in mcp_tools)
except Exception as e:
    check("MCP tools/list", False, str(e))

# 4. Letta: MCP server registered
print("\n[4] Letta — MCP registration")
try:
    servers = letta_get("/v1/tools/mcp/servers")
    has_han_solo = "han-solo" in servers
    check("han-solo MCP server registered", has_han_solo)
    if has_han_solo:
        check("server URL correct",
              "han-solo-mcp.onrender.com" in servers["han-solo"].get("server_url", ""),
              servers["han-solo"].get("server_url", ""))
except Exception as e:
    check("Letta MCP servers", False, str(e))

# 5. Letta: Ren's tool set
print("\n[5] Letta — Ren's tools")
try:
    agent = letta_get(f"/v1/agents/{AGENT_ID}")
    tools = agent.get("tools", [])
    han_tools = {t["name"] for t in tools if "mcp:han-solo" in t.get("tags", [])}
    write_tools = {t for t in han_tools if t.startswith("write_") or t in ("delete_t4_entry", "advance_phase")}

    check("Total tools on Ren", len(tools) > 10, f"{len(tools)} tools")
    check("Han-solo tools count", len(han_tools) == len(EXPECTED_HAN_SOLO_TOOLS),
          f"{len(han_tools)} attached, expected {len(EXPECTED_HAN_SOLO_TOOLS)}")
    check("No write tools on Ren", len(write_tools) == 0,
          f"write tools present: {write_tools}" if write_tools else "clean")
    for name in sorted(EXPECTED_HAN_SOLO_TOOLS):
        check(f"  Ren has: {name}", name in han_tools)
except Exception as e:
    check("Letta agent tools", False, str(e))

# 6. Core memory blocks
print("\n[6] Core memory blocks")
try:
    blocks = letta_get(f"/v1/agents/{AGENT_ID}/core-memory/blocks")
    block_map = {b["label"]: b for b in blocks}

    alc = block_map.get("always_loaded_core", {})
    alc_len = len(alc.get("value", ""))
    alc_limit = alc.get("limit", ALWAYS_LOADED_CORE_LIMIT)
    check("always_loaded_core exists", bool(alc))
    check("always_loaded_core within limit",
          alc_len < alc_limit,
          f"{alc_len:,} / {alc_limit:,} chars")
    check("always_loaded_core has get_skill", "get_skill" in alc.get("value", ""))
    check("always_loaded_core has list_skills", "list_skills" in alc.get("value", ""))

    pt = block_map.get("pending_thoughts", {})
    pt_len = len(pt.get("value", ""))
    check("pending_thoughts exists", bool(pt))
    check("pending_thoughts size reasonable",
          pt_len < PENDING_THOUGHTS_LIMIT,
          f"{pt_len:,} chars", warn=True)
except Exception as e:
    check("Core memory blocks", False, str(e))

# 7. T4 access
print("\n[7] T4 project memory")
try:
    projects = mcp_get("/api/t4/projects")
    project_slugs = [p["project_slug"] for p in projects] if isinstance(projects, list) else []
    check("T4 projects accessible", len(project_slugs) >= 3, f"{len(project_slugs)} projects: {project_slugs}")
except Exception as e:
    check("T4 projects", False, str(e))

# 8. Skills table
print("\n[8] Skills table")
try:
    skills = mcp_get("/api/skills/discover")
    check("Skills table accessible", "content" in skills or "phase_slug" in skills,
          f"slug={skills.get('phase_slug','?')} chars={len(skills.get('content',''))}")
    check("Skills table has content", len(skills.get("content", "")) > 100)
except Exception as e:
    # No skill for 'discover' might just mean it hasn't been seeded
    check("Skills table accessible", False, str(e), warn=True)

# 9. Jobs state
print("\n[9] Jobs")
try:
    jobs = mcp_get("/api/jobs-status")
    check("Automated jobs enabled", not jobs.get("paused", True),
          "paused" if jobs.get("paused") else "running")
except Exception as e:
    check("Jobs status", False, str(e))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'─' * 50}")
passed = sum(1 for ok, _ in results if ok)
total  = len(results)
failed = [line for ok, line in results if not ok]

print(f"  {passed}/{total} checks passed")
if failed:
    print(f"\n  Failed:")
    for line in failed:
        print(f"  {line}")
print()

sys.exit(0 if not failed else 1)
