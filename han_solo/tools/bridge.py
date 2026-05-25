"""
Bridge tools — synchronous communication between Claude Code and Ren.
Claude calls send_to_ren mid-session; Ren responds via her Letta context.
The exchange is recorded in Ren's conversation history but does not appear
in the workspace UI.
"""
import asyncio

from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import letta_client as letta
from .. import db


def register(server: FastMCP) -> None:

    @server.tool()
    async def send_to_ren(message: str) -> str:
        """
        Send a message to Ren synchronously and return her response.

        Use this when you need Ren's input during a session:
        - Architecture decisions before implementing
        - Assumption audits on a proposed approach
        - Continuity check ("why did we build it this way?")
        - Handoff notes at session close — ask Ren for her notes, then write
          both sections to T4 via write_t4_entry("han-solo", "handoff",
          entry_id="daily-active", content="...")

        The exchange lands in Ren's Letta context so she remembers it.
        It does not appear in the workspace UI chat history.

        Returns Ren's response as plain text.
        """
        get_current_user()

        prefixed = f"[FROM CLAUDE CODE]\n\n{message}"
        try:
            messages, _, usage = await letta.send_chat_message(prefixed, "Claude Code")
        except Exception as exc:
            return f"Bridge unavailable — Ren did not respond: {exc}"

        asyncio.create_task(db.write_usage_log("bridge", **usage))
        return "\n\n".join(messages) if messages else "No response from Ren."
