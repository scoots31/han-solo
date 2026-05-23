"""
Session brief tools — retrieve pending thoughts and generate the session opening brief.
Ren reads this at session start and decides what to surface, when, and how.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import letta_client as letta
from .. import db


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
            project_state = (await letta.read_core_block("project_state")).get("value", "")
        except Exception:
            project_state = ""

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

        ct = ZoneInfo("America/Chicago")
        now = datetime.now(tz=ct)
        current_datetime = now.strftime("%A, %B %-d, %Y — %-I:%M %p CT")

        return {
            "current_datetime": current_datetime,
            "always_loaded_core": always_loaded,
            "system_state": project_state,
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

    @server.tool()
    async def check_memory_health() -> dict:
        """
        Check memory system health. Call this at every session start.

        Returns:
        - failed_transitions_24h: count of failed T1→T2 or T2→T3 promotions in last 24 hours
        - failed_transitions: list of what failed and why
        - capture: transcript capture status (db_connected, last_write_at, consecutive_failures)

        Flag anything non-zero to Scott immediately.
        """
        get_current_user()
        failed = await db.get_failed_transitions(hours=24)
        capture = db.health_status()
        return {
            "failed_transitions_24h": len(failed),
            "failed_transitions": [
                {
                    "from_tier": f["from_tier"],
                    "to_tier": f["to_tier"],
                    "content_key": f["content_key"],
                    "error": f["error"],
                    "attempted_at": f["attempted_at"].isoformat() if f.get("attempted_at") else None,
                }
                for f in failed
            ],
            "capture": capture,
        }
