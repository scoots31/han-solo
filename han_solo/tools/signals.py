"""
Signal writing tools — all four taxonomy types written to archival memory (Store 4).

Signal types:
  relational  — how Scott and Ted actually operate; behavioural observations
  directional — where the work is going, decisions that shifted things
  ren         — Ren's own performance observations
  texture     — small moments; no noise filter; collected consistently
"""
import json
from datetime import date

from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from ..validation import assert_can_write_signal
from .. import letta_client as letta

VALID_SIGNAL_TYPES = {"relational", "directional", "ren", "texture"}
VALID_SUBJECTS = {"scott", "ted", "ren", "project", "framework"}


def register(server: FastMCP) -> None:

    @server.tool()
    async def write_signal(
        signal_type: str,
        subject: str,
        content: str,
        session_date: str = "",
    ) -> str:
        """
        Write a signal to archival memory.

        signal_type: relational | directional | ren | texture
        subject: scott | ted | ren | project | framework
        content: the signal text — specific, not a characterisation
        session_date: YYYY-MM-DD (defaults to today if omitted)

        Texture signals have no noise filter — write small things as they happen.
        """
        user = get_current_user()

        if signal_type not in VALID_SIGNAL_TYPES:
            return f"Error: signal_type must be one of {sorted(VALID_SIGNAL_TYPES)}"
        if subject not in VALID_SUBJECTS:
            return f"Error: subject must be one of {sorted(VALID_SUBJECTS)}"

        if subject in {"scott", "ted", "ren"}:
            assert_can_write_signal(subject, user)

        today = session_date or date.today().isoformat()
        tags = ["signal", signal_type, subject, today, f"author:{user.id}"]
        result = await letta.insert_passage(content=content, tags=tags)
        return f"Signal written [{signal_type}/{subject}] id={result.get('id', 'unknown')}"

    @server.tool()
    async def search_signals(
        query: str,
        signal_type: str = "",
        subject: str = "",
        limit: int = 20,
    ) -> list[dict]:
        """
        Semantic search across archival signals.

        query: natural language — what you're looking for
        signal_type: filter to relational | directional | ren | texture (optional)
        subject: filter to scott | ted | ren | project | framework (optional)
        limit: max results (default 20)
        """
        get_current_user()
        passages = await letta.search_passages(query=query, limit=limit)
        results = []
        for p in passages:
            tags = p.get("metadata_", {}).get("tags", [])
            if signal_type and signal_type not in tags:
                continue
            if subject and subject not in tags:
                continue
            if "signal" not in tags:
                continue
            results.append({
                "id": p.get("id"),
                "type": next((t for t in tags if t in VALID_SIGNAL_TYPES), "unknown"),
                "subject": next((t for t in tags if t in VALID_SUBJECTS), "unknown"),
                "date": next((t for t in tags if len(t) == 10 and t[4] == "-"), "unknown"),
                "content": p.get("text", ""),
            })
        return results

    @server.tool()
    async def write_session_summary(summary: str, session_date: str = "") -> str:
        """
        Write a structured session-close summary to archival memory (Store 3).
        This is the raw material the scheduled Dreaming jobs process.

        Use the fixed structure: date/participants, decisions made, relational signals,
        texture signals, Ren self-observations, pending thoughts, open threads.
        """
        get_current_user()
        today = session_date or date.today().isoformat()
        tags = ["session_summary", today]
        result = await letta.insert_passage(content=summary, tags=tags)
        return f"Session summary written for {today}, id={result.get('id', 'unknown')}"
