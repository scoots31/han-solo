"""
Transcripts tool — search parsed Claude Code session transcripts.

Read-only. Allows Ren to search across all session transcripts stored
in the Han Solo DB, finding prior sessions by keyword.
"""
from mcp.server.fastmcp import FastMCP

from .. import db


def register(server: FastMCP) -> None:

    @server.tool()
    async def search_transcripts(query: str, limit: int = 10) -> str:
        """
        Search parsed Claude Code session transcripts by keyword.

        Searches the full conversation text of all stored sessions.
        Returns session IDs, timestamps, entry counts, and a content preview.

        query: One or more words to search for (all words must match).
        limit: Max results to return (default 10, max 50).
        """
        if not query.strip():
            return "Error: query is required"
        limit = min(max(1, limit), 50)
        results = await db.search_session_transcripts(query=query, limit=limit)
        if not results:
            return f"No sessions found matching '{query}'"
        lines = [f"Found {len(results)} session(s) matching '{query}':\n"]
        for r in results:
            started = r["started_at"].strftime("%Y-%m-%d %H:%M") if r.get("started_at") else "?"
            complete = "complete" if r.get("is_complete") else "in progress"
            preview = (r.get("preview") or "")[:300].replace("\n", " ")
            lines.append(
                f"• {r['session_id'][:16]}  {started}  {r['entry_count']} entries  [{complete}]\n"
                f"  {preview}"
            )
        return "\n".join(lines)
