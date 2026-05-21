"""
db.py — Direct PostgreSQL connection for raw transcript capture.

Separate from Letta's database access. This module owns the chat_transcripts
table — raw message capture that survives rollovers, restarts, and context crashes.

The transcripts table is the durable source the synthesis script reads from.
Letta's conversation store is volatile; this is not.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool: Optional[asyncpg.Pool] = None

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS notecards (
    id          SERIAL PRIMARY KEY,
    text        TEXT        NOT NULL,
    creator     TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'active',
    source      TEXT        NOT NULL DEFAULT 'manual',
    session_id  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notecards_status
    ON notecards(status, created_at DESC);
CREATE TABLE IF NOT EXISTS chat_transcripts (
    id          SERIAL PRIMARY KEY,
    session_id  TEXT        NOT NULL,
    role        TEXT        NOT NULL,
    name        TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed   BOOLEAN     NOT NULL DEFAULT FALSE,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_transcripts_session
    ON chat_transcripts(session_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_unprocessed
    ON chat_transcripts(processed, created_at);
CREATE TABLE IF NOT EXISTS han_solo_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
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
CREATE TABLE IF NOT EXISTS t4_entries (
    id           SERIAL PRIMARY KEY,
    project_slug TEXT        NOT NULL,
    entry_type   TEXT        NOT NULL,
    entry_id     TEXT        NOT NULL,
    parent_id    TEXT,
    content      TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_slug, entry_type, entry_id)
);
CREATE INDEX IF NOT EXISTS idx_t4_project
    ON t4_entries(project_slug, entry_type);
CREATE TABLE IF NOT EXISTS signals (
    id           SERIAL PRIMARY KEY,
    signal_type  TEXT        NOT NULL,
    subject      TEXT        NOT NULL,
    content      TEXT        NOT NULL,
    session_date DATE        NOT NULL,
    author       TEXT        NOT NULL DEFAULT 'synthesis',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_signals_type
    ON signals(signal_type, created_at DESC);
CREATE TABLE IF NOT EXISTS t4_projects (
    project_slug TEXT        PRIMARY KEY,
    owner        TEXT        NOT NULL DEFAULT 'scott',
    visibility   TEXT        NOT NULL DEFAULT 'private',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS skills (
    phase_slug   TEXT        PRIMARY KEY,
    layer        TEXT        NOT NULL DEFAULT 'phase-active',
    content      TEXT        NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
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
CREATE TABLE IF NOT EXISTS passage_enrichments (
    id              SERIAL PRIMARY KEY,
    passage_id      TEXT        NOT NULL,
    context_note    TEXT        NOT NULL,
    session_date    DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_enrichments_passage
    ON passage_enrichments(passage_id, created_at DESC);
CREATE TABLE IF NOT EXISTS memory_access_log (
    id              SERIAL PRIMARY KEY,
    search_query    TEXT        NOT NULL,
    passage_ids     TEXT[]      NOT NULL DEFAULT '{}',
    passage_count   INT         NOT NULL DEFAULT 0,
    used_in_response BOOLEAN    NOT NULL DEFAULT FALSE,
    session_id      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_access_log_session
    ON memory_access_log(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_log_time
    ON memory_access_log(created_at DESC);
"""

# Runs after CREATE_TABLE_SQL — backfills existing slugs as scott/private, idempotent
MIGRATE_T4_PROJECTS_SQL = """
INSERT INTO t4_projects (project_slug, owner, visibility)
SELECT DISTINCT project_slug, 'scott', 'private'
FROM t4_entries
ON CONFLICT (project_slug) DO NOTHING;
"""

# Health tracking — last successful write timestamp
_last_write_at: Optional[datetime] = None
_write_failure_count: int = 0


async def init_pool() -> None:
    global _pool
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set — transcript capture disabled")
        return
    try:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        async with _pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)
            await conn.execute(MIGRATE_T4_PROJECTS_SQL)
        logger.info("Transcript DB pool ready")
    except Exception as e:
        logger.error("Failed to init transcript DB pool: %s", e)
        _pool = None


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def write_message(session_id: str, role: str, name: str, content: str) -> bool:
    """Write a single message to the transcript table. Returns True on success."""
    global _last_write_at, _write_failure_count
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chat_transcripts (session_id, role, name, content)
                VALUES ($1, $2, $3, $4)
                """,
                session_id, role, name, content,
            )
        _last_write_at = datetime.now(timezone.utc)
        _write_failure_count = 0
        return True
    except Exception as e:
        _write_failure_count += 1
        logger.error("Transcript write failed (failure #%d): %s", _write_failure_count, e)
        return False


async def write_messages_bulk(session_id: str, messages: list[dict]) -> bool:
    """Write a list of {role, name, content} messages. Used for pre-rollover archive."""
    global _last_write_at, _write_failure_count
    if not _pool or not messages:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO chat_transcripts (session_id, role, name, content)
                VALUES ($1, $2, $3, $4)
                """,
                [(session_id, m["role"], m["name"], m["content"]) for m in messages],
            )
        _last_write_at = datetime.now(timezone.utc)
        _write_failure_count = 0
        return True
    except Exception as e:
        _write_failure_count += 1
        logger.error("Bulk transcript write failed: %s", e)
        return False


async def get_unprocessed_sessions() -> list[dict]:
    """Return distinct sessions with unprocessed messages, oldest first."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT session_id, MIN(created_at) as first_msg, COUNT(*) as msg_count
                FROM chat_transcripts
                WHERE processed = FALSE
                GROUP BY session_id
                ORDER BY first_msg ASC
                """
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to fetch unprocessed sessions: %s", e)
        return []


async def get_session_messages(session_id: str) -> list[dict]:
    """Return all messages for a session in order."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, name, content, created_at
                FROM chat_transcripts
                WHERE session_id = $1
                ORDER BY created_at ASC
                """,
                session_id,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to fetch session messages: %s", e)
        return []


async def mark_session_processed(session_id: str) -> bool:
    """Mark all messages in a session as processed. Only call after confirmed write to Letta."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE chat_transcripts
                SET processed = TRUE, processed_at = NOW()
                WHERE session_id = $1
                """,
                session_id,
            )
        return True
    except Exception as e:
        logger.error("Failed to mark session processed: %s", e)
        return False


async def purge_old_processed(days: int = 5) -> int:
    """Delete processed transcripts older than N days. Returns count deleted."""
    if not _pool:
        return 0
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM chat_transcripts
                WHERE processed = TRUE
                  AND processed_at < NOW() - INTERVAL '1 day' * $1
                """,
                days,
            )
        count = int(result.split()[-1])
        logger.info("Purged %d old processed transcript rows", count)
        return count
    except Exception as e:
        logger.error("Failed to purge old transcripts: %s", e)
        return 0


async def get_active_agent_id() -> Optional[str]:
    """Return the last persisted active agent ID, or None if not set."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM han_solo_config WHERE key = 'active_agent_id'"
            )
        return row["value"] if row else None
    except Exception as e:
        logger.error("Failed to read active_agent_id: %s", e)
        return None


async def set_active_agent_id(agent_id: str) -> bool:
    """Persist the active agent ID so it survives service restarts."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO han_solo_config (key, value, updated_at)
                VALUES ('active_agent_id', $1, NOW())
                ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()
                """,
                agent_id,
            )
        logger.info("Persisted active_agent_id: %s", agent_id)
        return True
    except Exception as e:
        logger.error("Failed to persist active_agent_id: %s", e)
        return False


def health_status() -> dict:
    """Return current transcript capture health for the memory panel."""
    return {
        "db_connected": _pool is not None,
        "last_write_at": _last_write_at.isoformat() if _last_write_at else None,
        "consecutive_failures": _write_failure_count,
    }


async def log_transition(from_tier: str, to_tier: str, content_key: str) -> Optional[int]:
    """Insert a memory_transitions row with status='pending'. Returns the row id."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memory_transitions (from_tier, to_tier, content_key, status)
                VALUES ($1, $2, $3, 'pending')
                RETURNING id
                """,
                from_tier, to_tier, content_key,
            )
        return row["id"] if row else None
    except Exception as e:
        logger.error("Failed to log transition: %s", e)
        return None


async def complete_transition(transition_id: int) -> bool:
    """Mark a memory_transitions row as succeeded."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_transitions
                SET status = 'success', completed_at = NOW()
                WHERE id = $1
                """,
                transition_id,
            )
        return True
    except Exception as e:
        logger.error("Failed to complete transition %d: %s", transition_id, e)
        return False


async def fail_transition(transition_id: int, error: str) -> bool:
    """Mark a memory_transitions row as failed with error detail."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_transitions
                SET status = 'failed', completed_at = NOW(), error = $2
                WHERE id = $1
                """,
                transition_id, error,
            )
        return True
    except Exception as e:
        logger.error("Failed to record transition failure %d: %s", transition_id, e)
        return False


async def get_jobs_paused() -> bool:
    """Return True if automated jobs (dream, synthesize) are paused."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM han_solo_config WHERE key = 'jobs_paused'"
            )
        return row["value"] == "true" if row else False
    except Exception as e:
        logger.error("Failed to read jobs_paused: %s", e)
        return False


async def write_t4_entry(
    project_slug: str,
    entry_type: str,
    entry_id: str,
    content: str,
    parent_id: str | None,
    behavior: str,  # "write_once" | "upsert" | "append"
) -> dict:
    """Write a T4 entry. Behavior is derived by the tool layer before calling here."""
    if not _pool:
        return {"error": "DB not connected"}
    try:
        async with _pool.acquire() as conn:
            if behavior == "write_once":
                existing = await conn.fetchrow(
                    "SELECT id FROM t4_entries WHERE project_slug=$1 AND entry_type=$2 AND entry_id=$3",
                    project_slug, entry_type, entry_id,
                )
                if existing:
                    return {"error": f"Entry {entry_type}/{entry_id} already exists for {project_slug} — write_once rejects overwrites"}
                row = await conn.fetchrow(
                    """
                    INSERT INTO t4_entries (project_slug, entry_type, entry_id, parent_id, content)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, project_slug, entry_type, entry_id, created_at
                    """,
                    project_slug, entry_type, entry_id, parent_id, content,
                )
            elif behavior == "upsert":
                row = await conn.fetchrow(
                    """
                    INSERT INTO t4_entries (project_slug, entry_type, entry_id, parent_id, content)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (project_slug, entry_type, entry_id)
                    DO UPDATE SET content=$5, parent_id=$4, updated_at=NOW()
                    RETURNING id, project_slug, entry_type, entry_id, updated_at
                    """,
                    project_slug, entry_type, entry_id, parent_id, content,
                )
            elif behavior == "append":
                existing = await conn.fetchrow(
                    "SELECT id, content FROM t4_entries WHERE project_slug=$1 AND entry_type=$2 AND entry_id=$3",
                    project_slug, entry_type, entry_id,
                )
                if existing:
                    merged = existing["content"] + "\n\n---\n\n" + content
                    row = await conn.fetchrow(
                        """
                        UPDATE t4_entries SET content=$4, updated_at=NOW()
                        WHERE project_slug=$1 AND entry_type=$2 AND entry_id=$3
                        RETURNING id, project_slug, entry_type, entry_id, updated_at
                        """,
                        project_slug, entry_type, entry_id, merged,
                    )
                else:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO t4_entries (project_slug, entry_type, entry_id, parent_id, content)
                        VALUES ($1, $2, $3, $4, $5)
                        RETURNING id, project_slug, entry_type, entry_id, created_at
                        """,
                        project_slug, entry_type, entry_id, parent_id, content,
                    )
            else:
                return {"error": f"Unknown behavior: {behavior}"}
        return dict(row) if row else {"error": "No row returned"}
    except Exception as e:
        logger.error("Failed to write T4 entry: %s", e)
        return {"error": str(e)}


async def get_t4_entry(
    project_slug: str,
    entry_type: str,
    entry_id: str,
) -> dict | None:
    """Fetch a single T4 entry by project + type + id. Returns None if not found."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, project_slug, entry_type, entry_id, parent_id,
                       content, created_at, updated_at
                FROM t4_entries
                WHERE project_slug=$1 AND entry_type=$2 AND entry_id=$3
                """,
                project_slug, entry_type, entry_id,
            )
        return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to get T4 entry: %s", e)
        return None


async def search_t4(
    project_slug: str,
    query: str,
    entry_type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Full-text search across T4 entries for a project."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            if entry_type:
                rows = await conn.fetch(
                    """
                    SELECT id, project_slug, entry_type, entry_id, parent_id,
                           content, updated_at
                    FROM t4_entries
                    WHERE project_slug=$1 AND entry_type=$2
                      AND content ILIKE $3
                    ORDER BY updated_at DESC
                    LIMIT $4
                    """,
                    project_slug, entry_type, f"%{query}%", limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, project_slug, entry_type, entry_id, parent_id,
                           content, updated_at
                    FROM t4_entries
                    WHERE project_slug=$1 AND content ILIKE $2
                    ORDER BY updated_at DESC
                    LIMIT $3
                    """,
                    project_slug, f"%{query}%", limit,
                )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to search T4: %s", e)
        return []


async def delete_t4_entry(
    project_slug: str,
    entry_type: str,
    entry_id: str | None = None,
) -> dict:
    """
    Delete a T4 entry (or all entries of a type for a project).
    If entry_id is None, deletes all entries matching project_slug + entry_type.
    Returns count of deleted rows.
    """
    if not _pool:
        return {"error": "no pool"}
    try:
        async with _pool.acquire() as conn:
            if entry_id:
                result = await conn.execute(
                    "DELETE FROM t4_entries WHERE project_slug=$1 AND entry_type=$2 AND entry_id=$3",
                    project_slug, entry_type, entry_id,
                )
            else:
                result = await conn.execute(
                    "DELETE FROM t4_entries WHERE project_slug=$1 AND entry_type=$2",
                    project_slug, entry_type,
                )
        count = int(result.split()[-1])
        return {"deleted": count}
    except Exception as e:
        logger.error("Failed to delete T4 entry: %s", e)
        return {"error": str(e)}


async def ensure_project_exists(project_slug: str, owner: str = "scott") -> None:
    """Create a t4_projects record for a slug if one doesn't exist yet."""
    if not _pool:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO t4_projects (project_slug, owner, visibility)
                VALUES ($1, $2, 'private')
                ON CONFLICT (project_slug) DO NOTHING
                """,
                project_slug, owner,
            )
    except Exception as e:
        logger.error("ensure_project_exists failed for %s: %s", project_slug, e)


async def update_project_visibility(project_slug: str, visibility: str) -> bool:
    """Set visibility to 'private' or 'shared'. Returns True on success."""
    if visibility not in ("private", "shared"):
        return False
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE t4_projects SET visibility=$1 WHERE project_slug=$2",
                visibility, project_slug,
            )
        return result == "UPDATE 1"
    except Exception as e:
        logger.error("update_project_visibility failed for %s: %s", project_slug, e)
        return False


async def list_t4_projects() -> list[dict]:
    """
    Return all projects with owner, visibility, current_phase, and slice counts.
    Joins t4_projects for ownership data; falls back gracefully if row missing.
    """
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            slugs = await conn.fetch(
                "SELECT DISTINCT project_slug FROM t4_entries ORDER BY project_slug"
            )
            results = []
            for row in slugs:
                slug = row["project_slug"]
                proj_row = await conn.fetchrow(
                    "SELECT owner, visibility FROM t4_projects WHERE project_slug=$1",
                    slug,
                )
                phase_row = await conn.fetchrow(
                    "SELECT content FROM t4_entries WHERE project_slug=$1 AND entry_type='current_phase'",
                    slug,
                )
                counts = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE entry_type='slice') AS total_slices,
                        COUNT(*) FILTER (WHERE entry_type='slice' AND content ILIKE '%**Status:** Done%') AS done_slices,
                        COUNT(*) FILTER (WHERE entry_type='phase') AS total_phases,
                        COUNT(*) FILTER (WHERE entry_type='deliverable') AS total_deliverables
                    FROM t4_entries WHERE project_slug=$1
                    """,
                    slug,
                )
                results.append({
                    "project_slug": slug,
                    "owner": proj_row["owner"] if proj_row else "scott",
                    "visibility": proj_row["visibility"] if proj_row else "private",
                    "current_phase": phase_row["content"] if phase_row else None,
                    "total_slices": counts["total_slices"],
                    "done_slices": counts["done_slices"],
                    "total_phases": counts["total_phases"],
                    "total_deliverables": counts["total_deliverables"],
                })
        return results
    except Exception as e:
        logger.error("Failed to list T4 projects: %s", e)
        return []


async def list_t4_entries_by_type(project_slug: str, entry_type: str) -> list[dict]:
    """List all T4 entries of a given type for a project, ordered by entry_id."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, project_slug, entry_type, entry_id, parent_id,
                       content, updated_at
                FROM t4_entries
                WHERE project_slug=$1 AND entry_type=$2
                ORDER BY entry_id
                """,
                project_slug, entry_type,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to list T4 entries: %s", e)
        return []


async def set_jobs_paused(paused: bool) -> bool:
    """Set the jobs_paused flag. Returns True on success."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO han_solo_config (key, value, updated_at)
                VALUES ('jobs_paused', $1, NOW())
                ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()
                """,
                "true" if paused else "false",
            )
        logger.info("jobs_paused set to %s", paused)
        return True
    except Exception as e:
        logger.error("Failed to set jobs_paused: %s", e)
        return False


async def create_notecard(
    text: str, creator: str, source: str = "manual", session_id: str | None = None
) -> dict:
    """Insert a notecard. Returns the new row as a dict."""
    if not _pool:
        return {}
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO notecards (text, creator, source, session_id)
                VALUES ($1, $2, $3, $4)
                RETURNING id, text, creator, status, source, session_id, created_at
                """,
                text, creator, source, session_id,
            )
        return dict(row)
    except Exception as e:
        logger.error("Failed to create notecard: %s", e)
        return {}


async def list_notecards(status: str | None = None) -> list[dict]:
    """
    List notecards ordered newest first.
    status=None returns active + completed.
    status='archived' returns only archived.
    status='active'|'completed' returns that single status.
    """
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            if status is None:
                rows = await conn.fetch(
                    """
                    SELECT id, text, creator, status, source, session_id, created_at
                    FROM notecards
                    WHERE status IN ('active', 'completed')
                    ORDER BY created_at DESC
                    """
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, text, creator, status, source, session_id, created_at
                    FROM notecards
                    WHERE status = $1
                    ORDER BY created_at DESC
                    """,
                    status,
                )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to list notecards: %s", e)
        return []


async def update_notecard_status(notecard_id: int, status: str) -> bool:
    """Update a notecard's status. Returns True on success."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE notecards
                SET status = $1, updated_at = NOW()
                WHERE id = $2
                """,
                status, notecard_id,
            )
        return result == "UPDATE 1"
    except Exception as e:
        logger.error("Failed to update notecard %d: %s", notecard_id, e)
        return False


async def create_signal(signal_type: str, subject: str, content: str, session_date: str, author: str = "synthesis") -> dict | None:
    """Insert a signal. Returns the new row as a dict."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO signals (signal_type, subject, content, session_date, author)
                VALUES ($1, $2, $3, $4::date, $5)
                RETURNING id, signal_type, subject, content, session_date, author, created_at
                """,
                signal_type, subject, content, session_date, author,
            )
        return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to create signal: %s", e)
        return None


async def list_signals(signal_type: str | None = None, limit: int = 200) -> list[dict]:
    """List signals newest first, optionally filtered by type."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            if signal_type:
                rows = await conn.fetch(
                    "SELECT id, signal_type, subject, content, session_date, author, created_at FROM signals WHERE signal_type = $1 ORDER BY created_at DESC LIMIT $2",
                    signal_type, limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT id, signal_type, subject, content, session_date, author, created_at FROM signals ORDER BY created_at DESC LIMIT $1",
                    limit,
                )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to list signals: %s", e)
        return []


async def get_failed_transitions(hours: int = 24) -> list[dict]:
    """Return failed memory_transitions from the last N hours for health check."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, attempted_at, from_tier, to_tier, content_key, error
                FROM memory_transitions
                WHERE status = 'failed'
                  AND attempted_at > NOW() - INTERVAL '1 hour' * $1
                ORDER BY attempted_at DESC
                """,
                hours,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to fetch failed transitions: %s", e)
        return []


async def get_skill(phase_slug: str) -> Optional[dict]:
    """Return skill record for a given phase slug, or None if not found."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT phase_slug, layer, content, updated_at FROM skills WHERE phase_slug = $1",
                phase_slug,
            )
        return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to get skill %s: %s", phase_slug, e)
        return None


async def write_connection(
    passage_id_a: str,
    passage_id_b: str,
    relationship: str,
    confidence: float,
    grounding: str | None = None,
    curator_run_id: str | None = None,
) -> bool:
    """Upsert a memory connection. Updates confidence and grounding if higher-confidence run."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
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
        logger.error("Failed to write connection: %s", e)
        return False


async def get_connections_for_passage(passage_id: str, min_confidence: float = 0.7) -> list[dict]:
    """Return all connections for a passage (bidirectional), ordered by confidence desc."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, passage_id_a, passage_id_b, relationship, confidence, grounding, created_at,
                    CASE WHEN passage_id_a = $1 THEN passage_id_b ELSE passage_id_a END AS connected_passage_id
                FROM memory_connections
                WHERE (passage_id_a = $1 OR passage_id_b = $1)
                  AND confidence >= $2
                ORDER BY confidence DESC
                """,
                passage_id, min_confidence,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get connections for %s: %s", passage_id, e)
        return []


async def log_memory_access(
    search_query: str,
    passage_ids: list[str],
    used_in_response: bool,
    session_id: str | None = None,
) -> bool:
    """Log an archival search: what was queried, what was found, whether it was used."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_access_log
                    (search_query, passage_ids, passage_count, used_in_response, session_id)
                VALUES ($1, $2, $3, $4, $5)
                """,
                search_query, passage_ids, len(passage_ids), used_in_response, session_id,
            )
        return True
    except Exception as e:
        logger.error("Failed to log memory access: %s", e)
        return False


async def get_memory_access_patterns(days: int = 30) -> dict:
    """
    Aggregate access log into pattern analysis:
    - hot passages (accessed most)
    - cold passages (never accessed, from all known passage IDs)
    - dry wells (queries returning no results)
    - false positives (found but not used)
    Returns dict with each category.
    """
    if not _pool:
        return {}
    try:
        async with _pool.acquire() as conn:
            # Query frequency and usage rates per passage
            passage_rows = await conn.fetch(
                """
                SELECT
                    unnest(passage_ids) AS passage_id,
                    COUNT(*) AS access_count,
                    SUM(CASE WHEN used_in_response THEN 1 ELSE 0 END) AS used_count
                FROM memory_access_log
                WHERE created_at > NOW() - INTERVAL '1 day' * $1
                GROUP BY passage_id
                ORDER BY access_count DESC
                """,
                days,
            )

            # Dry wells: searches that returned nothing
            dry_wells = await conn.fetch(
                """
                SELECT search_query, COUNT(*) AS occurrences
                FROM memory_access_log
                WHERE passage_count = 0
                  AND created_at > NOW() - INTERVAL '1 day' * $1
                GROUP BY search_query
                ORDER BY occurrences DESC
                LIMIT 20
                """,
                days,
            )

            # False positives: found passages but didn't use them
            false_positives = await conn.fetch(
                """
                SELECT
                    unnest(passage_ids) AS passage_id,
                    COUNT(*) AS found_count,
                    SUM(CASE WHEN used_in_response THEN 1 ELSE 0 END) AS used_count
                FROM memory_access_log
                WHERE passage_count > 0
                  AND created_at > NOW() - INTERVAL '1 day' * $1
                GROUP BY passage_id
                HAVING SUM(CASE WHEN used_in_response THEN 1 ELSE 0 END) = 0
                ORDER BY found_count DESC
                LIMIT 20
                """,
                days,
            )

            # Total searches in period
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM memory_access_log WHERE created_at > NOW() - INTERVAL '1 day' * $1",
                days,
            )

        hot = [
            {"passage_id": r["passage_id"], "access_count": r["access_count"],
             "used_count": r["used_count"],
             "use_rate": round(r["used_count"] / r["access_count"], 2) if r["access_count"] else 0}
            for r in passage_rows[:20]
        ]
        cold_ids = [r["passage_id"] for r in passage_rows if r["access_count"] == 0]

        return {
            "period_days": days,
            "total_searches": total,
            "hot_passages": hot,
            "cold_passage_ids": cold_ids,
            "dry_wells": [{"query": r["search_query"], "occurrences": r["occurrences"]} for r in dry_wells],
            "false_positives": [
                {"passage_id": r["passage_id"], "found_count": r["found_count"]}
                for r in false_positives
            ],
        }
    except Exception as e:
        logger.error("Failed to get memory access patterns: %s", e)
        return {}


async def write_curator_flag(
    passage_id: str,
    flag_type: str,
    note: str | None = None,
    related_passage_id: str | None = None,
    curator_run_id: str | None = None,
) -> bool:
    """Write a curator quality flag for a passage. flag_type: near_duplicate | self_containment."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
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
        logger.error("Failed to write curator flag: %s", e)
        return False


async def get_curator_flags(flag_type: str | None = None, resolved: bool = False) -> list[dict]:
    """Return curator flags, optionally filtered by type and resolution status."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            if flag_type:
                rows = await conn.fetch(
                    """
                    SELECT id, passage_id, flag_type, related_passage_id, note, resolved, created_at
                    FROM curator_flags
                    WHERE flag_type = $1 AND resolved = $2
                    ORDER BY created_at DESC
                    """,
                    flag_type, resolved,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, passage_id, flag_type, related_passage_id, note, resolved, created_at
                    FROM curator_flags
                    WHERE resolved = $1
                    ORDER BY created_at DESC
                    """,
                    resolved,
                )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get curator flags: %s", e)
        return []


async def write_passage_enrichment(
    passage_id: str, context_note: str, session_date: str | None = None
) -> bool:
    """Append a context note to a passage. Called by Ren when a passage is meaningfully retrieved."""
    if not _pool:
        return False
    try:
        from datetime import date as _date
        date_val = session_date or _date.today().isoformat()
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO passage_enrichments (passage_id, context_note, session_date)
                VALUES ($1, $2, $3::date)
                """,
                passage_id, context_note, date_val,
            )
        return True
    except Exception as e:
        logger.error("Failed to write passage enrichment: %s", e)
        return False


async def get_passage_enrichments(passage_id: str) -> list[dict]:
    """Return all enrichments for a passage, newest first."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, context_note, session_date, created_at
                FROM passage_enrichments
                WHERE passage_id = $1
                ORDER BY created_at DESC
                """,
                passage_id,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get passage enrichments for %s: %s", passage_id, e)
        return []


async def upsert_skill(phase_slug: str, content: str, layer: str = "phase-active") -> bool:
    """Insert or update a skill record. Returns True on success."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO skills (phase_slug, layer, content, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (phase_slug) DO UPDATE
                    SET content = EXCLUDED.content,
                        layer = EXCLUDED.layer,
                        updated_at = NOW()
                """,
                phase_slug, layer, content,
            )
        return True
    except Exception as e:
        logger.error("Failed to upsert skill %s: %s", phase_slug, e)
        return False
