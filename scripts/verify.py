"""
verify.py — Han Solo system health check.

Verifies the full stack in one pass: local environment, tokens, Letta agent,
tool counts, core memory blocks, portrait integrity, T4 access, skills table,
session logs, docs site, MCP server registration, and Render cold-start timing.

Run any time you want to confirm the system is intact — especially after
any architecture session that touches tools, memory blocks, or DB schema.

Usage:
    python3 scripts/verify.py

Environment vars required:
    MCP_URL     — Han Solo MCP server URL (default: https://han-solo-mcp.onrender.com)
    MCP_TOKEN   — bearer token (USER_TOKEN_SCOTT or system token)
    LETTA_URL   — Letta server URL (default: https://han-solo-letta.onrender.com)
    LETTA_KEY   — Letta API key (set in ~/.zshenv)
    AGENT_ID    — Ren's agent ID
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Config — fall back to known values if env not set
# ---------------------------------------------------------------------------

MCP_URL       = os.environ.get("MCP_URL", "https://han-solo-mcp.onrender.com")
MCP_TOKEN     = os.environ.get("MCP_TOKEN", "RHcpXjeAJlu_DzhYplsLaUOUSGVrU-gceamJQoXb81Q")
LETTA_URL     = os.environ.get("LETTA_URL", "https://han-solo-letta.onrender.com")
LETTA_KEY     = os.environ.get("LETTA_API_KEY") or os.environ.get("LETTA_KEY", "")
AGENT_ID      = os.environ.get("AGENT_ID", "agent-fe4a3d5b-bb51-458e-92f1-6a1ee5b0ce94")
DOCS_URL      = "https://han-solo-docs.pages.dev"
HAN_SOLO_REPO = os.path.expanduser("~/Developer/han-solo")
REN_LOCAL_PY  = os.path.expanduser("~/Developer/ren-local/ren-local.py")

# Expected state — update these when the architecture changes
EXPECTED_HAN_SOLO_TOOLS = {
    "search_t4", "get_t4_entry", "search_signals",
    "get_session_brief", "list_notecards",
    "get_skill", "list_skills",
}
EXPECTED_SKILLS = {
    "discover", "tech-context", "design-sprint", "prd-to-plan",
    "solo-build", "solo-qa", "deploy", "brainstorming", "data-scaffold",
}
EXPECTED_PORTRAIT_SUBJECTS = ["scott", "ren", "ted"]
ALWAYS_LOADED_CORE_LIMIT   = 10_000
PENDING_THOUGHTS_LIMIT     = 50_000
COLD_START_WARN_SECS       = 10.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_cold_starts: list[tuple[str, float]] = []


def _timed_request(url: str, headers: dict, data: bytes | None = None,
                   method: str = "GET", timeout: int = 30) -> tuple[bytes, float]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return body, time.time() - t0


def _record_render(service: str, elapsed: float) -> None:
    if elapsed > COLD_START_WARN_SECS:
        _cold_starts.append((service, elapsed))


def mcp_get(path: str) -> tuple[dict | list, float]:
    body, elapsed = _timed_request(
        f"{MCP_URL}{path}", {"Authorization": f"Bearer {MCP_TOKEN}"}
    )
    return json.loads(body), elapsed


def letta_get(path: str) -> tuple[dict | list, float]:
    body, elapsed = _timed_request(
        f"{LETTA_URL}{path}", {"Authorization": f"Bearer {LETTA_KEY}"}
    )
    return json.loads(body), elapsed


def http_check(url: str, timeout: int = 15) -> tuple[int, float]:
    req = urllib.request.Request(url, headers={"User-Agent": "verify.py"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    return status, time.time() - t0


def mcp_tools_list() -> set[str]:
    """Call MCP tools/list via JSON-RPC and return tool name set."""
    headers = {
        "Authorization": f"Bearer {MCP_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    payload = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 1}).encode()
    body, _ = _timed_request(f"{MCP_URL}/mcp", headers, data=payload,
                              method="POST", timeout=30)
    for line in body.decode().split("\n"):
        if line.startswith("data:"):
            result = json.loads(line[5:])
            return {t["name"] for t in result["result"]["tools"]}
    return set()


PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results: list[tuple[bool, str]] = []


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

t_start = time.time()

# 0. Local environment — things that must be wired on this machine for framework work
print("\n[0] Local environment")

check("LETTA_API_KEY set", bool(LETTA_KEY),
      f"{len(LETTA_KEY)} chars" if LETTA_KEY else "not set — add to ~/.zshenv")

check("ren-local CLI exists", os.path.exists(REN_LOCAL_PY), REN_LOCAL_PY)

try:
    r = subprocess.run(
        ["python3", REN_LOCAL_PY, "read", "--last", "1"],
        capture_output=True, text=True, timeout=10
    )
    check("ren-local responds", r.returncode == 0,
          "ok" if r.returncode == 0 else r.stderr.strip()[:80])
except Exception as e:
    check("ren-local responds", False, str(e))

check("wrangler available", bool(shutil.which("wrangler")),
      shutil.which("wrangler") or "not found — Cloudflare deploys will fail")

try:
    r = subprocess.run(
        ["ssh", "-T", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=8", "git@github.com"],
        capture_output=True, text=True, timeout=12
    )
    ssh_out = (r.stdout + r.stderr).lower()
    check("git SSH key valid", "successfully authenticated" in ssh_out,
          "authenticated" if "successfully authenticated" in ssh_out else ssh_out[:80])
except Exception as e:
    check("git SSH key valid", False, str(e))

try:
    branch = subprocess.run(
        ["git", "-C", HAN_SOLO_REPO, "branch", "--show-current"],
        capture_output=True, text=True
    ).stdout.strip()
    check("han-solo repo on main", branch == "main", f"branch: {branch}")

    dirty = subprocess.run(
        ["git", "-C", HAN_SOLO_REPO, "status", "--porcelain"],
        capture_output=True, text=True
    ).stdout.strip()
    check("han-solo repo clean", not dirty,
          "clean" if not dirty else f"{len(dirty.splitlines())} uncommitted change(s)")

    sb_line = subprocess.run(
        ["git", "-C", HAN_SOLO_REPO, "status", "-sb"],
        capture_output=True, text=True
    ).stdout.splitlines()[0]
    unpushed = "ahead" in sb_line
    check("han-solo repo pushed", not unpushed,
          "up to date" if not unpushed else sb_line.strip(), warn=unpushed)
except Exception as e:
    check("han-solo repo state", False, str(e))


# 1. MCP server health
print("\n[1] MCP server")
try:
    health, elapsed = mcp_get("/health")
    _record_render("MCP server", elapsed)
    check("MCP health", health.get("status") == "ok", str(health))
    check("Ren agent ID in health", "ren_agent" in health, health.get("ren_agent", "missing"))
except Exception as e:
    check("MCP reachable", False, str(e))

# 2. Token auth
print("\n[2] Token auth")
try:
    me, _ = mcp_get("/api/me")
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
    servers, elapsed = letta_get("/v1/tools/mcp/servers")
    _record_render("Letta", elapsed)
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
    agent, _ = letta_get(f"/v1/agents/{AGENT_ID}")
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

# 6. Core memory blocks — existence, size limits, and portrait integrity
print("\n[6] Core memory blocks")
try:
    blocks, _ = letta_get(f"/v1/agents/{AGENT_ID}/core-memory/blocks")
    block_map = {b["label"]: b for b in blocks}

    alc = block_map.get("always_loaded_core", {})
    alc_len = len(alc.get("value", ""))
    alc_limit = alc.get("limit", ALWAYS_LOADED_CORE_LIMIT)
    check("always_loaded_core exists", bool(alc))
    check("always_loaded_core within limit",
          alc_len < alc_limit, f"{alc_len:,} / {alc_limit:,} chars")
    check("always_loaded_core has get_skill", "get_skill" in alc.get("value", ""))
    check("always_loaded_core has list_skills", "list_skills" in alc.get("value", ""))

    pt = block_map.get("pending_thoughts", {})
    pt_len = len(pt.get("value", ""))
    check("pending_thoughts exists", bool(pt))
    check("pending_thoughts size reasonable",
          pt_len < PENDING_THOUGHTS_LIMIT, f"{pt_len:,} chars", warn=True)

    # memory_landscape tells Ren how to search — if missing her retrieval breaks silently
    ml = block_map.get("memory_landscape", {})
    check("memory_landscape exists", bool(ml),
          f"{len(ml.get('value', '')):,} chars" if ml else "missing — Ren's search guidance is gone")

    # Portrait blocks give Ren relational context for each person
    for subject in EXPECTED_PORTRAIT_SUBJECTS:
        forming = block_map.get(f"{subject}_portrait_forming", {})
        trusted = block_map.get(f"{subject}_portrait_trusted", {})
        has_portrait = bool(forming) or bool(trusted)
        chars = len(forming.get("value", "")) + len(trusted.get("value", ""))
        check(f"{subject} portrait exists", has_portrait,
              f"{chars:,} chars" if has_portrait else f"no portrait block found",
              warn=(subject == "ted"))  # Ted's portrait not yet established — warn not fail
except Exception as e:
    check("Core memory blocks", False, str(e))

# 7. T4 access
print("\n[7] T4 project memory")
try:
    projects, _ = mcp_get("/api/t4/projects")
    project_slugs = [p["project_slug"] for p in projects] if isinstance(projects, list) else []
    check("T4 projects accessible", len(project_slugs) >= 3,
          f"{len(project_slugs)} projects: {project_slugs}")
except Exception as e:
    check("T4 projects", False, str(e))

# 8. Skills table — verify all expected phase skills are seeded, not just one
print("\n[8] Skills table")
found_skills: set[str] = set()
try:
    for slug in sorted(EXPECTED_SKILLS):
        try:
            skill, _ = mcp_get(f"/api/skills/{slug}")
            has_content = "content" in skill or "phase_slug" in skill
            chars = len(skill.get("content", ""))
            if has_content and chars > 100:
                found_skills.add(slug)
            check(f"  skill: {slug}", has_content and chars > 100, f"{chars:,} chars")
        except Exception as e:
            check(f"  skill: {slug}", False, str(e)[:60])
    check("All expected skills present", found_skills == EXPECTED_SKILLS,
          f"{len(found_skills)}/{len(EXPECTED_SKILLS)}"
          + (f" — missing: {EXPECTED_SKILLS - found_skills}" if found_skills != EXPECTED_SKILLS else ""))
except Exception as e:
    check("Skills table", False, str(e))

# 9. Jobs state
print("\n[9] Jobs")
try:
    jobs, _ = mcp_get("/api/jobs-status")
    check("Automated jobs enabled", not jobs.get("paused", True),
          "paused" if jobs.get("paused") else "running")
except Exception as e:
    check("Jobs status", False, str(e))

# 10. Session logs — proves the logbook write path and DB round-trip are working
print("\n[10] Session logs")
try:
    logs, _ = mcp_get("/api/session-logs")
    log_list = logs if isinstance(logs, list) else logs.get("logs", [])
    check("Session logs accessible", True, f"{len(log_list)} entries")
    check("Session logs has data", len(log_list) > 0,
          "logbook populated" if log_list else "empty — write path may be broken")
except Exception as e:
    check("Session logs", False, str(e))

# 11. Docs site — confirms Cloudflare is serving the public site
print("\n[11] Docs site")
try:
    status, elapsed = http_check(DOCS_URL)
    check("Docs site reachable", status == 200, f"HTTP {status}  {elapsed:.1f}s")
    check("Docs site response time", elapsed < 5.0,
          f"{elapsed:.1f}s" if elapsed < 5.0 else f"{elapsed:.1f}s — may be cold", warn=True)
except Exception as e:
    check("Docs site reachable", False, str(e))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

total_elapsed = time.time() - t_start
print(f"\n{'─' * 50}")
passed = sum(1 for ok, _ in results if ok)
total  = len(results)
failed = [line for ok, line in results if not ok]

print(f"  {passed}/{total} checks passed  ({total_elapsed:.1f}s total)")

if _cold_starts:
    print(f"\n  ⚠️   Render cold start detected:")
    for service, t in _cold_starts:
        print(f"        {service}: {t:.1f}s — first Ren response this session will be slow")

if failed:
    print(f"\n  Failed:")
    for line in failed:
        print(f"  {line}")
print()

sys.exit(0 if not failed else 1)
