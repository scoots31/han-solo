"""
synthesize.py — Ren's synthesis engine.

Reads unprocessed raw transcripts from the chat_transcripts table,
calls Anthropic directly (claude-sonnet-4-6) to synthesize meaning,
writes results to Ren's memory via the MCP, then marks sessions processed.

Runs on a schedule (every few hours via launchd or Render cron).
Completely independent of Letta's dreaming — they run in parallel and
both contribute to Ren's memory.

Usage:
    python3 scripts/synthesize.py

Environment vars required:
    DATABASE_URL        — PostgreSQL connection string (same as MCP service)
    ANTHROPIC_API_KEY   — direct Anthropic API key for Sonnet synthesis
    MCP_URL             — Han Solo MCP server URL
    MCP_TOKEN           — bearer token (USER_TOKEN_SCOTT or system token)
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error
import asyncio
import asyncpg
from datetime import datetime, timedelta, timezone

DATABASE_URL      = os.environ["DATABASE_URL"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MCP_URL           = os.environ.get("MCP_URL", "https://han-solo-mcp.onrender.com")
MCP_TOKEN         = os.environ["MCP_TOKEN"]

SYNTHESIS_MODEL = "claude-sonnet-4-6"

SYNTHESIS_PROMPT = """You are synthesizing a raw conversation transcript between Scott and Ren into structured memory for Ren's next session.

The transcript is raw chat — every message as it was sent. Your job is to extract what matters and write it in two forms:

1. PENDING_THOUGHTS UPDATE — a tight session brief Scott will read at the start of the next session. Format:
   - What happened (2-4 bullet points, specific)
   - Decisions made (list only actual decisions, not discussions)
   - Open threads (things explicitly left unresolved)
   - What Ren should flag at session start (anomalies, follow-ups, things Scott was waiting on)

2. ARCHIVAL SIGNALS — 2-5 specific signals worth keeping long-term. Each signal should be:
   - Type: relational | directional | ren | texture
   - Subject: scott | ted | ren | project | framework
   - Content: one specific observation. Not a summary. Something that would be useful to surface in a future semantic search.

Return as JSON:
{
  "pending_thoughts_addition": "...",
  "signals": [
    {"type": "...", "subject": "...", "content": "..."},
    ...
  ]
}

Transcript to synthesize:
"""


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _anthropic_request(messages: list[dict]) -> str:
    """Call Anthropic API directly. Returns assistant text."""
    payload = {
        "model": SYNTHESIS_MODEL,
        "max_tokens": 2048,
        "messages": messages,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        method="POST",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        result = json.loads(r.read())
    return result["content"][0]["text"]


def _mcp_request(method: str, path: str, body: dict | None = None) -> dict:
    """Call the Han Solo MCP REST API."""
    url = f"{MCP_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {MCP_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"MCP {method} {path} → HTTP {e.code}: {body_text}")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

async def get_unprocessed_sessions(pool: asyncpg.Pool) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT session_id, MIN(created_at) as first_msg, COUNT(*) as msg_count
        FROM chat_transcripts
        WHERE processed = FALSE
        GROUP BY session_id
        ORDER BY first_msg ASC
        """
    )
    return [dict(r) for r in rows]


async def get_session_messages(pool: asyncpg.Pool, session_id: str) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT role, name, content, created_at
        FROM chat_transcripts
        WHERE session_id = $1
        ORDER BY created_at ASC
        """,
        session_id,
    )
    return [dict(r) for r in rows]


async def mark_processed(pool: asyncpg.Pool, session_id: str) -> None:
    await pool.execute(
        """
        UPDATE chat_transcripts
        SET processed = TRUE, processed_at = NOW()
        WHERE session_id = $1
        """,
        session_id,
    )


async def purge_old(pool: asyncpg.Pool, days: int = 5) -> int:
    result = await pool.execute(
        """
        DELETE FROM chat_transcripts
        WHERE processed = TRUE
          AND processed_at < NOW() - INTERVAL '1 day' * $1
        """,
        days,
    )
    return int(result.split()[-1])


# ---------------------------------------------------------------------------
# Transition logging (memory_transitions table)
# ---------------------------------------------------------------------------

async def log_transition(pool: asyncpg.Pool, from_tier: str, to_tier: str, content_key: str) -> int | None:
    """Insert a pending transition record. Returns id, or None on failure."""
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO memory_transitions (from_tier, to_tier, content_key, status)
            VALUES ($1, $2, $3, 'pending')
            RETURNING id
            """,
            from_tier, to_tier, content_key,
        )
        return row["id"] if row else None
    except Exception as e:
        print(f"  ✗ Failed to log transition: {e}", file=sys.stderr)
        return None


async def complete_transition(pool: asyncpg.Pool, transition_id: int) -> None:
    try:
        await pool.execute(
            "UPDATE memory_transitions SET status = 'success', completed_at = NOW() WHERE id = $1",
            transition_id,
        )
    except Exception as e:
        print(f"  ✗ Failed to complete transition {transition_id}: {e}", file=sys.stderr)


async def fail_transition(pool: asyncpg.Pool, transition_id: int, error: str) -> None:
    try:
        await pool.execute(
            "UPDATE memory_transitions SET status = 'failed', completed_at = NOW(), error = $2 WHERE id = $1",
            transition_id, error,
        )
    except Exception as e:
        print(f"  ✗ Failed to record transition failure {transition_id}: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# T1 → T2 promotion
# ---------------------------------------------------------------------------

# Matches the header written by synthesize.py: SYNTHESIS [YYYY-MM-DD session XXXXXXXX]:
_SYNTHESIS_HEADER_RE = re.compile(r"^SYNTHESIS \[(\d{4}-\d{2}-\d{2}) session ([^\]]+)\]:")


def _parse_pending_thoughts(text: str) -> list[dict]:
    """
    Split pending_thoughts into sections.

    Returns a list of dicts:
        {
            "raw": str,          # full section text
            "is_synthesis": bool,
            "date": date | None, # only set for synthesis entries
            "session_key": str,  # short session id, or empty string
        }

    Sections are separated by lines that contain only "---" (with optional
    surrounding blank lines). Non-synthesis sections are left untouched.
    """
    # Normalise separators: any line that is just "---" with optional whitespace
    parts = re.split(r"\n\s*---\s*\n", text)
    sections = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        first_line = part.split("\n", 1)[0].strip()
        m = _SYNTHESIS_HEADER_RE.match(first_line)
        if m:
            date_str, session_key = m.group(1), m.group(2)
            try:
                entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                entry_date = None
            sections.append({
                "raw": part,
                "is_synthesis": True,
                "date": entry_date,
                "session_key": session_key.strip(),
            })
        else:
            sections.append({
                "raw": part,
                "is_synthesis": False,
                "date": None,
                "session_key": "",
            })
    return sections


async def promote_old_entries(
    pool: asyncpg.Pool,
    current_pt: str,
    cutoff_days: int = 3,
) -> tuple[str, int]:
    """
    Promote pending_thoughts SYNTHESIS entries older than cutoff_days to T2 archival.
    Trim to the 2 most recent SYNTHESIS entries after confirmed promotions.

    Returns (new_pending_thoughts_value, promoted_count).

    Write-before-trim invariant: an entry is only removed from T1 after the T2
    write is confirmed. If T2 write fails, the entry stays, the failure is logged,
    and the function moves on.
    """
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=cutoff_days)

    sections = _parse_pending_thoughts(current_pt)
    synthesis_sections = [s for s in sections if s["is_synthesis"]]
    other_sections = [s for s in sections if not s["is_synthesis"]]

    if not synthesis_sections:
        return current_pt, 0

    # Sort synthesis entries newest-first so we can identify the 2 to keep
    dated = [s for s in synthesis_sections if s["date"] is not None]
    undated = [s for s in synthesis_sections if s["date"] is None]
    dated.sort(key=lambda s: s["date"], reverse=True)

    to_keep = dated[:2]
    keep_keys = {s["session_key"] for s in to_keep}

    old_entries = [
        s for s in dated[2:]  # anything beyond the 2 most recent
        if s["date"] <= cutoff    # and older than cutoff
    ]
    # Also promote dated entries beyond index 2 that are within cutoff — keep them for now
    # (they'll get promoted on a future run once they age out)

    promoted = 0
    failed_to_promote = []

    for entry in old_entries:
        content_key = f"pt_{entry['session_key']}" if entry["session_key"] else f"pt_{entry['date']}"
        transition_id = await log_transition(pool, "T1", "T2", content_key)

        # Write to T2 archival via MCP
        archival_text = (
            f"[T2 promoted from pending_thoughts | session {entry['session_key']} | {entry['date']}]\n"
            f"{entry['raw']}"
        )
        try:
            _mcp_request("POST", "/api/write-signal", {
                "signal_type": "texture",
                "subject": "ren",
                "content": archival_text,
                "session_date": entry["date"].isoformat(),
            })
            if transition_id is not None:
                await complete_transition(pool, transition_id)
            promoted += 1
            print(f"  ✓ Promoted T1→T2: {content_key}")
        except Exception as e:
            err = str(e)
            if transition_id is not None:
                await fail_transition(pool, transition_id, err)
            failed_to_promote.append(entry["session_key"])
            print(f"  ✗ T2 write failed for {content_key}: {err}", file=sys.stderr)
            # Entry stays in T1 — do not add to keep set exclusion
            keep_keys.add(entry["session_key"])

    if promoted == 0 and not old_entries:
        # Nothing to promote, nothing to trim
        return current_pt, 0

    # Rebuild pending_thoughts: non-synthesis content + the 2 most recent synthesis entries
    # + any dated entries within cutoff that weren't in the top 2 (kept until they age out)
    # + any entries that failed to promote
    surviving_synthesis = []
    for s in dated:
        if s["session_key"] in keep_keys or s["date"] > cutoff:
            surviving_synthesis.append(s)

    # Always keep undated synthesis entries (Ren wrote them, Ren trims them)
    surviving_synthesis.extend(undated)

    all_surviving = other_sections + surviving_synthesis
    if not all_surviving:
        return "", promoted

    rebuilt = "\n\n---\n".join(s["raw"] for s in all_surviving)
    return rebuilt, promoted


# ---------------------------------------------------------------------------
# T2 → T3 promotion (tag tier:foundational on old archival passages)
# ---------------------------------------------------------------------------

FOUNDATIONAL_TAG = "[tier:foundational]"
T3_AGE_DAYS = 90


def _tag_foundational(pool, cutoff_days: int = T3_AGE_DAYS) -> tuple[int, int]:
    """
    Synchronous wrapper: find archival passages older than cutoff_days that
    aren't already tagged tier:foundational, rewrite them with the tag, then
    delete the originals.

    Returns (tagged_count, failed_count).
    Write-before-delete invariant: old passage is only deleted after new one confirmed.
    """
    import asyncio as _asyncio

    async def _run():
        tagged, failed = 0, 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)

        try:
            resp = _mcp_request("GET", f"/api/archival-passages?limit=500")
            passages = resp if isinstance(resp, list) else resp.get("passages", resp.get("data", []))
        except Exception as e:
            print(f"  ✗ Could not fetch archival passages for T3 pass: {e}", file=sys.stderr)
            return 0, 0

        candidates = []
        for p in passages:
            if FOUNDATIONAL_TAG in p.get("text", ""):
                continue  # already tagged
            created_str = p.get("created_at", "")
            if not created_str:
                continue
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if created < cutoff:
                candidates.append(p)

        if not candidates:
            print("  — No archival passages eligible for T3 tagging")
            return 0, 0

        print(f"  Found {len(candidates)} passage(s) eligible for T3 tagging")

        for p in candidates:
            passage_id = p["id"]
            original_text = p["text"]
            tagged_text = f"{FOUNDATIONAL_TAG}\n{original_text}"
            content_key = f"archival_{passage_id[:8]}"

            transition_id = await log_transition(pool, "T2", "T3", content_key)

            # 1. Write new tagged passage
            try:
                _mcp_request("POST", "/api/write-signal", {
                    "signal_type": "texture",
                    "subject": "ren",
                    "content": tagged_text,
                    "session_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                })
            except Exception as e:
                err = f"T3 write failed: {e}"
                if transition_id:
                    await fail_transition(pool, transition_id, err)
                print(f"  ✗ {err}", file=sys.stderr)
                failed += 1
                continue

            # 2. Delete old untagged passage — only after write confirmed
            try:
                _mcp_request("POST", "/api/archival-passage/delete", {"id": passage_id})
                if transition_id:
                    await complete_transition(pool, transition_id)
                tagged += 1
                print(f"  ✓ Tagged T2→T3: {content_key}")
            except Exception as e:
                # New tagged version exists, old untagged also exists — log for cleanup
                err = f"T3 delete failed (duplicate exists): {e}"
                if transition_id:
                    await fail_transition(pool, transition_id, err)
                print(f"  ✗ {err}", file=sys.stderr)
                failed += 1

        return tagged, failed

    return _asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def format_transcript(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        ts = m["created_at"].strftime("%H:%M") if m.get("created_at") else ""
        lines.append(f"[{ts}] {m['name']}: {m['content']}")
    return "\n".join(lines)


def synthesize_transcript(transcript_text: str) -> dict:
    """Call Anthropic and parse the JSON response."""
    prompt = SYNTHESIS_PROMPT + transcript_text
    response = _anthropic_request([{"role": "user", "content": prompt}])

    # Strip markdown code fences if present
    text = response.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()

    return json.loads(text)


def write_to_letta(synthesis: dict, session_id: str) -> bool:
    """
    Write synthesized content to Ren's memory via MCP REST API.
    Returns True only if all writes confirmed — mark processed only after this.
    """
    pending = synthesis.get("pending_thoughts_addition", "").strip()
    signals = synthesis.get("signals", [])

    success = True

    # Read current pending_thoughts, append new content
    if pending:
        try:
            current = _mcp_request("GET", "/api/memory-panel")
            blocks = current.get("blocks", [])
            pt_block = next((b for b in blocks if b["label"] == "pending_thoughts"), None)
            current_pt = pt_block["value"] if pt_block else ""

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            new_pt = f"{current_pt}\n\n---\nSYNTHESIS [{today} session {session_id[:8]}]:\n{pending}".strip()

            _mcp_request("POST", "/api/write-core-block", {
                "label": "pending_thoughts",
                "value": new_pt,
            })
            print(f"  ✓ pending_thoughts updated")
        except Exception as e:
            print(f"  ✗ pending_thoughts write failed: {e}", file=sys.stderr)
            success = False

    # Write archival signals
    for sig in signals:
        try:
            _mcp_request("POST", "/api/write-signal", {
                "signal_type": sig["type"],
                "subject": sig["subject"],
                "content": sig["content"],
                "session_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })
            print(f"  ✓ signal [{sig['type']}/{sig['subject']}] written")
        except Exception as e:
            print(f"  ✗ signal write failed: {e}", file=sys.stderr)
            success = False

    return success


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_ENSURE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS memory_transitions (
    id           SERIAL PRIMARY KEY,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    from_tier    TEXT        NOT NULL,
    to_tier      TEXT        NOT NULL,
    content_key  TEXT        NOT NULL,
    status       TEXT        NOT NULL,
    completed_at TIMESTAMPTZ,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_transitions_status
    ON memory_transitions(status, attempted_at);
"""


async def run():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Synthesis starting...")

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)

    try:
        await pool.execute(_ENSURE_TABLES_SQL)
        sessions = await get_unprocessed_sessions(pool)

        if not sessions:
            print("No unprocessed sessions.")
        else:
            print(f"Found {len(sessions)} unprocessed session(s).")

        for session in sessions:
            session_id = session["session_id"]
            msg_count = session["msg_count"]
            print(f"\nProcessing session {session_id[:8]}... ({msg_count} messages)")

            messages = await get_session_messages(pool, session_id)
            if not messages:
                continue

            transcript_text = format_transcript(messages)

            try:
                synthesis = synthesize_transcript(transcript_text)
            except Exception as e:
                print(f"  ✗ Synthesis failed: {e}", file=sys.stderr)
                continue

            wrote_ok = write_to_letta(synthesis, session_id)

            if wrote_ok:
                await mark_processed(pool, session_id)
                print(f"  ✓ Session marked processed")
            else:
                print(f"  ✗ Not marking processed — writes incomplete", file=sys.stderr)

        # T1 → T2 promotion: promote and trim pending_thoughts
        print("\nRunning T1→T2 promotion check...")
        try:
            current = _mcp_request("GET", "/api/memory-panel")
            blocks = current.get("blocks", [])
            pt_block = next((b for b in blocks if b["label"] == "pending_thoughts"), None)
            current_pt = pt_block["value"] if pt_block else ""

            if current_pt:
                new_pt, promoted_count = await promote_old_entries(pool, current_pt)
                if promoted_count > 0:
                    _mcp_request("POST", "/api/write-core-block", {
                        "label": "pending_thoughts",
                        "value": new_pt,
                    })
                    print(f"  ✓ pending_thoughts trimmed after {promoted_count} promotion(s)")
                else:
                    print("  — No entries eligible for promotion")
            else:
                print("  — pending_thoughts is empty, nothing to promote")
        except Exception as e:
            print(f"  ✗ Promotion check failed: {e}", file=sys.stderr)

        # T2 → T3 promotion: tag old archival passages tier:foundational
        print("\nRunning T2→T3 foundational tagging pass...")
        try:
            tagged, tag_failed = _tag_foundational(pool, cutoff_days=T3_AGE_DAYS)
            if tagged:
                print(f"  ✓ Tagged {tagged} passage(s) as tier:foundational")
            if tag_failed:
                print(f"  ✗ {tag_failed} passage(s) failed — logged in memory_transitions")
        except Exception as e:
            print(f"  ✗ T3 tagging pass failed: {e}", file=sys.stderr)

        # Purge old processed transcripts
        purged = await purge_old(pool, days=5)
        if purged:
            print(f"\nPurged {purged} old processed transcript rows (>5 days)")

    finally:
        await pool.close()

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Synthesis complete.")


if __name__ == "__main__":
    asyncio.run(run())
