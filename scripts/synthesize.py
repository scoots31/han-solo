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
import sys
import urllib.request
import urllib.error
import asyncio
import asyncpg
from datetime import datetime, timezone

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

async def run():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Synthesis starting...")

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)

    try:
        sessions = await get_unprocessed_sessions(pool)

        if not sessions:
            print("No unprocessed sessions. Nothing to do.")
            return

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

        # Purge old processed transcripts
        purged = await purge_old(pool, days=5)
        if purged:
            print(f"\nPurged {purged} old processed transcript rows (>5 days)")

    finally:
        await pool.close()

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Synthesis complete.")


if __name__ == "__main__":
    asyncio.run(run())
