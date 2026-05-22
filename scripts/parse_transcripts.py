"""
parse_transcripts.py — Claude Code session transcript parser.

Reads JSONL session files from ~/.claude/projects/, extracts meaningful entries
(user messages, assistant responses, tool calls, bash commands, file ops),
and pushes parsed sessions to Han Solo via POST /api/transcripts.

Maintains a local watermark file so each run only processes new entries.
Runs via LaunchAgent every 30 minutes — no Anthropic API calls, no token usage.

Usage:
    python3 scripts/parse_transcripts.py [--backfill-days N] [--dry-run]

    --backfill-days N  Process sessions from the last N days (default: 0 = incremental only)
    --dry-run          Parse and print without POSTing to Han Solo
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MCP_URL       = os.environ.get("MCP_URL", "https://han-solo-mcp.onrender.com")
MCP_TOKEN     = os.environ.get("MCP_TOKEN", "RHcpXjeAJlu_DzhYplsLaUOUSGVrU-gceamJQoXb81Q")
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
PROJECT_NAME    = "Apps"
PROJECT_DIR     = CLAUDE_PROJECTS / "-Users-scottheinemeier-Apps"
WATERMARK_FILE  = Path.home() / ".claude" / "transcript_watermark.json"

# Entry types we care about — everything else is noise
MEANINGFUL_TYPES = {"user", "assistant"}
# Tool call content types to extract
TOOL_TYPES = {"tool_use", "tool_result"}


# ---------------------------------------------------------------------------
# Watermark — tracks last line processed per session file
# ---------------------------------------------------------------------------

def load_watermark() -> dict:
    if WATERMARK_FILE.exists():
        try:
            return json.loads(WATERMARK_FILE.read_text())
        except Exception:
            pass
    return {}


def save_watermark(watermark: dict) -> None:
    WATERMARK_FILE.write_text(json.dumps(watermark, indent=2))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def extract_text(content) -> str:
    """Extract plain text from a content block (str or list of blocks)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", "").strip())
                elif block.get("type") == "tool_use":
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    # Summarize key inputs without dumping everything
                    summary = _summarize_tool_input(name, inp)
                    parts.append(f"[tool: {name}] {summary}")
                elif block.get("type") == "tool_result":
                    result_content = block.get("content", "")
                    preview = extract_text(result_content)[:200]
                    parts.append(f"[result] {preview}")
        return "\n".join(p for p in parts if p)
    return ""


def _summarize_tool_input(tool_name: str, inp: dict) -> str:
    """Produce a short readable summary of a tool call's inputs."""
    if tool_name in ("Bash", "bash"):
        cmd = inp.get("command", "")
        return cmd[:120] + ("..." if len(cmd) > 120 else "")
    if tool_name in ("Read", "read"):
        return inp.get("file_path", "")
    if tool_name in ("Edit", "edit"):
        path = inp.get("file_path", "")
        return f"{path}"
    if tool_name in ("Write", "write"):
        path = inp.get("file_path", "")
        return f"{path}"
    # MCP tools — show tool name + first string value
    for v in inp.values():
        if isinstance(v, str) and v:
            return v[:80]
    return json.dumps(inp)[:80] if inp else ""


def parse_entry(raw: dict) -> dict | None:
    """
    Convert one raw JSONL entry to a structured parsed entry.
    Returns None for noise entries (queue-ops, system, titles, etc).
    """
    entry_type = raw.get("type", "")
    timestamp = raw.get("timestamp", "")

    if entry_type == "user":
        msg = raw.get("message", {})
        content = msg.get("content", "")
        text = extract_text(content)
        if not text:
            return None
        # Skip tool results surfaced as user messages (they're captured via assistant)
        if isinstance(content, list) and all(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        ):
            return None
        return {"type": "user", "timestamp": timestamp, "text": text[:1000]}

    if entry_type == "assistant":
        msg = raw.get("message", {})
        content = msg.get("content", [])
        if not isinstance(content, list):
            return None
        parts = []
        tool_calls = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                t = block.get("text", "").strip()
                if t:
                    parts.append(t[:500])
            elif block.get("type") == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                summary = _summarize_tool_input(name, inp)
                tool_calls.append({"tool": name, "summary": summary})
        if not parts and not tool_calls:
            return None
        result: dict = {"type": "assistant", "timestamp": timestamp}
        if parts:
            result["text"] = "\n".join(parts)
        if tool_calls:
            result["tool_calls"] = tool_calls
        return result

    return None


def parse_session_file(path: Path, start_line: int = 0) -> tuple[list, int]:
    """
    Parse a session JSONL file starting from start_line.
    Returns (parsed_entries, new_watermark_line).
    """
    entries = []
    line_num = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line_num < start_line:
                    line_num += 1
                    continue
                line_num += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    parsed = parse_entry(raw)
                    if parsed:
                        entries.append(parsed)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"  Error reading {path.name}: {e}", file=sys.stderr)
    return entries, line_num


def build_parsed_text(entries: list) -> str:
    """Flatten conversation text to a searchable string.
    Tool call summaries are excluded — they contain raw code/commands that
    trigger WAF rules. Structured tool data lives in parsed_content JSONB.
    """
    parts = []
    for e in entries:
        if e.get("text"):
            parts.append(e["text"])
    return "\n".join(parts)


def get_session_start(path: Path) -> str:
    """Extract timestamp of first entry in a session file."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    ts = raw.get("timestamp", "")
                    if ts:
                        return ts
                except Exception:
                    continue
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Han Solo API
# ---------------------------------------------------------------------------

def post_transcript(session_id: str, project: str, started_at: str,
                    all_entries: list, watermark: int, is_complete: bool,
                    dry_run: bool) -> bool:
    """POST the parsed session to Han Solo. Returns True on success."""
    parsed_text = build_parsed_text(all_entries)
    payload = {
        "session_id": session_id,
        "project": project,
        "started_at": started_at,
        "entry_count": len(all_entries),
        "is_complete": is_complete,
        "parsed_content": all_entries,
        "parsed_text": parsed_text,
        "watermark": watermark,
    }
    if dry_run:
        print(f"  [dry-run] Would POST {len(all_entries)} entries, {len(parsed_text)} chars")
        return True
    try:
        import gzip
        data = gzip.compress(json.dumps(payload).encode())
        req = urllib.request.Request(
            f"{MCP_URL}/api/transcripts",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {MCP_TOKEN}",
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception as e:
        print(f"  POST failed: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Claude Code transcripts and push to Han Solo")
    parser.add_argument("--backfill-days", type=int, default=0,
                        help="Process sessions from the last N days (0 = incremental only)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse without POSTing to Han Solo")
    args = parser.parse_args()

    if not PROJECT_DIR.exists():
        print(f"Project directory not found: {PROJECT_DIR}", file=sys.stderr)
        sys.exit(1)

    watermark = load_watermark()
    cutoff = None
    if args.backfill_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.backfill_days)
        print(f"Backfill mode: processing sessions since {cutoff.date()}")

    files = sorted(PROJECT_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    processed = skipped = errors = 0

    for jsonl_path in files:
        session_id = jsonl_path.stem
        mtime = datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=timezone.utc)

        # Skip files older than cutoff (backfill mode) or that haven't changed
        if cutoff and mtime < cutoff:
            continue

        current_lines = watermark.get(session_id, 0)
        total_lines = sum(1 for _ in jsonl_path.open("r", encoding="utf-8", errors="replace"))

        # Skip if nothing new
        if current_lines >= total_lines and not args.backfill_days:
            skipped += 1
            continue

        started_at = get_session_start(jsonl_path)
        start_from = 0 if args.backfill_days else current_lines

        print(f"Processing {session_id[:12]}... (lines {start_from}→{total_lines})")

        # For incremental: fetch existing entries from previous runs if we have a watermark
        # For backfill: start fresh
        new_entries, new_watermark = parse_session_file(jsonl_path, start_line=start_from)

        # Session is complete if file hasn't been modified in 2 hours
        age_hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
        is_complete = age_hours > 2

        if not new_entries and current_lines == new_watermark:
            skipped += 1
            continue

        # For incremental runs, we push only new entries and let the server append
        # For backfill, we send everything in one shot
        ok = post_transcript(
            session_id=session_id,
            project=PROJECT_NAME,
            started_at=started_at,
            all_entries=new_entries,
            watermark=new_watermark,
            is_complete=is_complete,
            dry_run=args.dry_run,
        )

        if ok:
            watermark[session_id] = new_watermark
            processed += 1
            print(f"  ✅ {len(new_entries)} entries, watermark={new_watermark}, complete={is_complete}")
        else:
            errors += 1
            print(f"  ❌ Failed to push {session_id[:12]}")

    if not args.dry_run:
        save_watermark(watermark)

    print(f"\nDone — {processed} processed, {skipped} skipped, {errors} errors")
    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
