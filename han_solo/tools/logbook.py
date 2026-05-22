"""
Logbook tool — write session log entries to the Han Solo project logbook.

Each entry captures what happened in a session, decisions made, open threads,
commit references, and a level tag (major/minor) for quick filtering.
"""
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import db


def register(server: FastMCP) -> None:

    @server.tool()
    async def write_session_log(
        summary: str,
        decisions: str = "",
        open_threads: str = "",
        commit_refs: str = "",
        tags: str = "",
        level: str = "minor",
        session_date: str = "",
    ) -> str:
        """
        Write a session log entry to the Han Solo project logbook.

        summary:      What happened this session — plain language, 3-5 sentences. Required.
        decisions:    Decisions made, one per line.
        open_threads: What's still open or deferred.
        commit_refs:  Comma-separated commit SHAs or PR links.
        tags:         Comma-separated system tags, e.g. "letta, render" or "db, mcp".
        level:        "major" (architecture change, significant decision) or "minor" (routine). Default: minor.
        session_date: ISO timestamp for the session, e.g. "2026-05-22T10:00:00Z". Defaults to now.
        """
        user = get_current_user()
        if level not in ("major", "minor"):
            return "Error: level must be 'major' or 'minor'"
        result = await db.create_session_log(
            summary=summary,
            decisions=decisions,
            open_threads=open_threads,
            commit_refs=commit_refs,
            tags=tags,
            level=level,
            created_by=user.id,
            session_date=session_date or None,
        )
        if not result:
            return "Error: failed to write session log"
        return f"Session log written — id={result['id']}, level={result['level']}"
