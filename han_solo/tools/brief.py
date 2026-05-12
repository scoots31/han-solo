"""
Session brief tools — retrieve pending thoughts and generate the session opening brief.
Ren reads this at session start and decides what to surface, when, and how.
"""
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import letta_client as letta


def register(server: FastMCP) -> None:

    @server.tool()
    async def get_session_brief() -> dict:
        """
        Retrieve the session opening brief: always-loaded core context,
        pending thoughts from last session, and the 5 most recent signals.
        Ren reads this at session open and decides what to surface unprompted.
        """
        get_current_user()

        try:
            always_loaded = (await letta.read_core_block("always_loaded_core")).get("value", "")
        except Exception:
            always_loaded = ""

        try:
            pending_thoughts = (await letta.read_core_block("pending_thoughts")).get("value", "")
        except Exception:
            pending_thoughts = ""

        try:
            recent = await letta.list_passages(limit=5)
            recent_signals = [
                {
                    "type": next(
                        (t for t in p.get("metadata_", {}).get("tags", [])
                         if t in {"relational", "directional", "ren", "texture", "session_summary"}),
                        "unknown",
                    ),
                    "content": p.get("text", "")[:300],
                    "date": next(
                        (t for t in p.get("metadata_", {}).get("tags", [])
                         if len(t) == 10 and t[4] == "-"),
                        "unknown",
                    ),
                }
                for p in recent
            ]
        except Exception:
            recent_signals = []

        return {
            "always_loaded_core": always_loaded,
            "pending_thoughts": pending_thoughts,
            "recent_signals": recent_signals,
        }

    @server.tool()
    async def write_pending_thoughts(thoughts: str) -> str:
        """
        Write Ren's pending thoughts for the next session — concerns, ideas, connections.
        Replaces the current pending_thoughts block entirely. Called at session close.
        """
        get_current_user()
        await letta.write_core_block("pending_thoughts", thoughts)
        return "Pending thoughts saved for next session."
