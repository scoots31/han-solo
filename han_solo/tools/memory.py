"""
Core memory tools — read/write named memory blocks (Store 4 always-loaded core).
"""
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from ..validation import assert_can_write_block
from .. import letta_client as letta


def register(server: FastMCP) -> None:

    @server.tool()
    async def read_core_memory(block_label: str) -> str:
        """
        Read a named core memory block.

        Common block labels:
        - always_loaded_core: the ~10-15 line always-loaded context
        - pending_thoughts: thoughts Ren flagged for next session
        - project_state: current phase, active slice, project metadata (JSON)
        - scott_portrait_forming / scott_portrait_trusted
        - ted_portrait_forming / ted_portrait_trusted
        - ren_portrait_forming / ren_portrait_trusted

        Returns the block value as a string.
        """
        get_current_user()
        block = await letta.read_core_block(block_label)
        return block.get("value", "")

    @server.tool()
    async def write_core_memory(block_label: str, value: str) -> str:
        """
        Write a named core memory block. Full replace — not an append.

        Protected blocks (user_registry, api_keys, visibility_settings, billing)
        require owner-level access and cannot be written by Claude.
        """
        user = get_current_user()
        assert_can_write_block(block_label, user)
        try:
            await letta.write_core_block(block_label, value)
        except Exception:
            await letta.create_core_block(block_label, value, limit=20000)
        return f"Block '{block_label}' updated."

    @server.tool()
    async def list_core_memory_blocks() -> list[dict]:
        """
        List all core memory blocks: label, character count, and first 100 chars.
        """
        get_current_user()
        blocks = await letta.list_core_blocks()
        return [
            {
                "label": b.get("label"),
                "chars": len(b.get("value", "")),
                "preview": b.get("value", "")[:100],
            }
            for b in blocks
        ]
