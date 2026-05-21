"""
curator.py — Memory connection curator.

Reads all archival passages from Ren's Letta memory via the Han Solo API,
identifies connections between them using Claude, and writes high-confidence
connections to the memory_connections table in Postgres.

Connections are additive — they never replace direct archival search. Ren
uses them to expand what she sees after a search, not as a substitute for it.

Only connections with confidence >= 0.7 are written. Bidirectional: every
A→B connection is also written as B→A so passage lookups work in either direction.

Runs after the synthesis cron, or independently on schedule.

Usage:
    python3 scripts/curator.py

Environment vars required:
    DATABASE_URL        — PostgreSQL connection string
    ANTHROPIC_API_KEY   — direct Anthropic API key for Claude Sonnet
    MCP_URL             — Han Solo MCP server URL
    MCP_TOKEN           — bearer token (system token)
"""
import json
import os
import sys
import uuid
import urllib.request
import urllib.error
import asyncio
import asyncpg
from datetime import datetime, timezone

DATABASE_URL      = os.environ["DATABASE_URL"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MCP_URL           = os.environ.get("MCP_URL", "https://han-solo-mcp.onrender.com")
MCP_TOKEN         = os.environ["MCP_TOKEN"]

CURATOR_MODEL    = "claude-sonnet-4-6"
BATCH_SIZE       = 20
MIN_CONFIDENCE   = 0.7

CURATOR_PROMPT = """You are analyzing a batch of memory passages from an AI assistant's archival memory.
Identify meaningful connections between pairs of passages.

For each connection return:
- passage_id_a: ID of the first passage (exact string from input)
- passage_id_b: ID of the second passage (exact string from input)
- relationship: one of: relates_to | follows_from | expands_on | references_same_entity | contradicts
- confidence: 0.0 to 1.0 — how certain you are this connection is real and specific
- grounding: one sentence explaining exactly WHY these connect — name the specific entity, project, decision, or thread they share

Rules:
- Only return connections with confidence >= 0.7
- Every connection must be grounded in specific shared content — a name, project, decision thread, or event. Not "both discuss AI."
- A passage may connect to multiple others
- Report each pair once only — do not duplicate A→B and B→A
- If no strong connections exist in this batch, return an empty list

Return only valid JSON:
{"connections": [{"passage_id_a": "...", "passage_id_b": "...", "relationship": "...", "confidence": 0.0, "grounding": "..."}, ...]}

Passages to analyze:
"""


QUALITY_SCAN_PROMPT = """You are auditing a batch of memory passages for two quality issues.

ISSUE 1 — NEAR DUPLICATES: Passages that say substantially the same thing and would cause
retrieval noise (returning two versions of the same information). Not just the same topic —
the same specific claim, decision, or observation.

ISSUE 2 — SELF-CONTAINMENT FAILURES: Passages that reference something without naming it,
making them impossible to understand or retrieve correctly in isolation. Examples: "the earlier
decision," "what we discussed," "as mentioned," "the approach we agreed on." The referenced
thing must be explicitly named inside the passage.

For each issue found, return the passage ID and a brief note explaining the problem.

Return only valid JSON:
{
  "near_duplicates": [
    {"passage_id_a": "...", "passage_id_b": "...", "note": "..."},
    ...
  ],
  "self_containment_failures": [
    {"passage_id": "...", "note": "..."},
    ...
  ]
}

If no issues found, return empty lists. Be conservative — only flag clear cases.

Passages to audit:
"""


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _anthropic_request(prompt: str) -> str:
    payload = {
        "model": CURATOR_MODEL,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
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
# Connection identification
# ---------------------------------------------------------------------------

def _format_batch(passages: list[dict]) -> str:
    lines = []
    for p in passages:
        lines.append(f"[ID: {p['id']}]\n{p['text']}\n")
    return "\n---\n".join(lines)


def _scan_quality(passages: list[dict]) -> dict:
    """Send a batch to Claude for near-duplicate and self-containment scanning."""
    if not passages:
        return {"near_duplicates": [], "self_containment_failures": []}
    batch_text = _format_batch(passages)
    prompt = QUALITY_SCAN_PROMPT + batch_text
    try:
        response = _anthropic_request(prompt)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0].strip()
        result = json.loads(text)
        return {
            "near_duplicates": result.get("near_duplicates", []),
            "self_containment_failures": result.get("self_containment_failures", []),
        }
    except Exception as e:
        print(f"  ✗ Quality scan failed for batch: {e}", file=sys.stderr)
        return {"near_duplicates": [], "self_containment_failures": []}


def _identify_connections(passages: list[dict]) -> list[dict]:
    """Send a batch of passages to Claude and return identified connections."""
    if len(passages) < 2:
        return []

    batch_text = _format_batch(passages)
    prompt = CURATOR_PROMPT + batch_text

    try:
        response = _anthropic_request(prompt)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0].strip()
        result = json.loads(text)
        return result.get("connections", [])
    except Exception as e:
        print(f"  ✗ Claude call failed for batch: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

async def get_jobs_paused(pool: asyncpg.Pool) -> bool:
    try:
        row = await pool.fetchrow("SELECT value FROM han_solo_config WHERE key = 'jobs_paused'")
        return row["value"] == "true" if row else False
    except Exception:
        return False


async def write_connection(
    pool: asyncpg.Pool,
    passage_id_a: str,
    passage_id_b: str,
    relationship: str,
    confidence: float,
    grounding: str | None,
    curator_run_id: str,
) -> bool:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_connections
                    (passage_id_a, passage_id_b, relationship, confidence, grounding, curator_run_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (passage_id_a, passage_id_b, relationship)
                DO UPDATE SET
                    confidence = GREATEST(memory_connections.confidence, EXCLUDED.confidence),
                    grounding = EXCLUDED.grounding,
                    curator_run_id = EXCLUDED.curator_run_id
                """,
                passage_id_a, passage_id_b, relationship, confidence, grounding, curator_run_id,
            )
        return True
    except Exception as e:
        print(f"  ✗ DB write failed for connection {passage_id_a[:8]}↔{passage_id_b[:8]}: {e}", file=sys.stderr)
        return False


_ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memory_connections (
    id              SERIAL PRIMARY KEY,
    passage_id_a    TEXT        NOT NULL,
    passage_id_b    TEXT        NOT NULL,
    relationship    TEXT        NOT NULL,
    confidence      FLOAT       NOT NULL DEFAULT 0.0,
    grounding       TEXT,
    curator_run_id  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(passage_id_a, passage_id_b, relationship)
);
CREATE INDEX IF NOT EXISTS idx_connections_a
    ON memory_connections(passage_id_a, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_connections_b
    ON memory_connections(passage_id_b, confidence DESC);
CREATE TABLE IF NOT EXISTS curator_flags (
    id                  SERIAL PRIMARY KEY,
    passage_id          TEXT        NOT NULL,
    flag_type           TEXT        NOT NULL,
    related_passage_id  TEXT,
    note                TEXT,
    resolved            BOOLEAN     NOT NULL DEFAULT FALSE,
    curator_run_id      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_curator_flags_type
    ON curator_flags(flag_type, resolved, created_at DESC);
"""


async def write_flag(
    pool: asyncpg.Pool, passage_id: str, flag_type: str,
    note: str | None, related_passage_id: str | None, curator_run_id: str,
) -> bool:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO curator_flags
                    (passage_id, flag_type, related_passage_id, note, curator_run_id)
                VALUES ($1, $2, $3, $4, $5)
                """,
                passage_id, flag_type, related_passage_id, note, curator_run_id,
            )
        return True
    except Exception as e:
        print(f"  ✗ Flag write failed: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run():
    run_id = str(uuid.uuid4())[:8]
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Curator starting... (run {run_id})")

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)

    try:
        await pool.execute(_ENSURE_TABLE_SQL)

        if await get_jobs_paused(pool):
            print("Automated jobs paused — skipping curator.")
            return

        # Fetch all archival passages
        print("Fetching archival passages...")
        try:
            resp = _mcp_request("GET", "/api/archival-passages?limit=500")
            passages = resp if isinstance(resp, list) else resp.get("passages", [])
        except Exception as e:
            print(f"✗ Could not fetch passages: {e}", file=sys.stderr)
            return

        passages = [p for p in passages if p.get("id") and p.get("text", "").strip()]
        print(f"Found {len(passages)} passages to analyze.")

        if len(passages) < 2:
            print("Not enough passages to find connections.")
            return

        # Process in batches
        total_found = 0
        total_written = 0
        batch_count = 0

        for i in range(0, len(passages), BATCH_SIZE):
            batch = passages[i:i + BATCH_SIZE]
            batch_count += 1
            print(f"\nBatch {batch_count} ({len(batch)} passages, idx {i}–{i+len(batch)-1})...")

            connections = _identify_connections(batch)
            high_conf = [c for c in connections if c.get("confidence", 0) >= MIN_CONFIDENCE]
            total_found += len(high_conf)
            print(f"  Found {len(connections)} connections, {len(high_conf)} above threshold.")

            # Quality scan: near-duplicates + self-containment failures
            quality = _scan_quality(batch)
            nd_count = len(quality["near_duplicates"])
            sc_count = len(quality["self_containment_failures"])
            if nd_count or sc_count:
                print(f"  Quality: {nd_count} near-duplicate pair(s), {sc_count} self-containment failure(s)")
            for nd in quality["near_duplicates"]:
                pid_a = nd.get("passage_id_a", "").strip()
                pid_b = nd.get("passage_id_b", "").strip()
                note = nd.get("note", "").strip() or None
                if pid_a and pid_b:
                    await write_flag(pool, pid_a, "near_duplicate", note, pid_b, run_id)
                    await write_flag(pool, pid_b, "near_duplicate", note, pid_a, run_id)
            for sc in quality["self_containment_failures"]:
                pid = sc.get("passage_id", "").strip()
                note = sc.get("note", "").strip() or None
                if pid:
                    await write_flag(pool, pid, "self_containment", note, None, run_id)

            for conn in high_conf:
                pid_a = conn.get("passage_id_a", "").strip()
                pid_b = conn.get("passage_id_b", "").strip()
                rel = conn.get("relationship", "").strip()
                conf = float(conn.get("confidence", 0))
                grounding = conn.get("grounding", "").strip() or None

                valid_rels = {"relates_to", "follows_from", "expands_on", "references_same_entity", "contradicts"}
                if not pid_a or not pid_b or rel not in valid_rels:
                    print(f"  ✗ Skipping malformed connection: {conn}")
                    continue

                # Write A→B
                ok_a = await write_connection(pool, pid_a, pid_b, rel, conf, grounding, run_id)
                # Write B→A (bidirectional — reversal curse prevention)
                ok_b = await write_connection(pool, pid_b, pid_a, rel, conf, grounding, run_id)

                if ok_a and ok_b:
                    total_written += 1
                    print(f"  ✓ {rel} ({conf:.2f}): {pid_a[:8]}↔{pid_b[:8]}")

    finally:
        await pool.close()

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Curator complete.")
    print(f"  Batches processed: {batch_count}")
    print(f"  Connections above threshold: {total_found}")
    print(f"  Connections written: {total_written}")


if __name__ == "__main__":
    asyncio.run(run())
