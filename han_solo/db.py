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
