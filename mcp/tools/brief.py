"""
Session brief tools — retrieve pending thoughts and generate the session opening brief.
Ren reads this at session start and decides what to surface, when, and how.
"""
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import letta_client as letta

mcp = FastMCP("brief")


@mcp.tool()
async def get_session_brief() -> dict:
    """
    Retrieve the session opening brief assembled by the nightly Dreaming job.
    Contains:
      - pending_thoughts: what Ren flagged at last session close
      - always_loaded_core: the current always-loaded identity context
      - recent_signals: last 5 signals from archival memory (most recent first)

    Ren reads this at session open and decides what to surface unprompted.
    """
    get_current_user()

    # Always-loaded core
    try:
        core_block = await letta.read_core_block("always_loaded_core")
        always_loaded = core_block.get("value", "")
    except Exception:
        always_loaded = ""

    # Pending thoughts
    try:
        pending_block = await letta.read_core_block("pending_thoughts")
        pending_thoughts = pending_block.get("value", "")
    except Exception:
        pending_thoughts = ""

    # Recent signals
    try:
        recent = await letta.list_passages(limit=5)
        recent_signals = [
            {
                "type": next(
                    (t for t in p.get("metadata_", {}).get("tags", [])
                     if t in {"relational", "directional", "ren", "texture", "session_summary"}),
                    "unknown"
                ),
                "content": p.get("text", "")[:300],
                "date": next(
                    (t for t in p.get("metadata_", {}).get("tags", [])
                     if len(t) == 10 and t[4] == "-"),
                    "unknown"
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


@mcp.tool()
async def write_pending_thoughts(thoughts: str) -> str:
    """
    Write Ren's pending thoughts for the next session — concerns, ideas, connections.
    Replaces the current pending_thoughts block entirely.

    Called at session close. The next session's brief will surface these.
    """
    get_current_user()
    await letta.write_core_block("pending_thoughts", thoughts)
    return "Pending thoughts saved for next session."
