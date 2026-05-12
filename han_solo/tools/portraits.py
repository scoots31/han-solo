"""
Living portrait tools — read/write forming and trusted portrait layers for
Scott, Ted, and Ren's self-portrait.
"""
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from ..validation import assert_can_write_block
from .. import letta_client as letta

VALID_PEOPLE = {"scott", "ted", "ren"}
VALID_LAYERS = {"forming", "trusted"}


def _label(person: str, layer: str) -> str:
    return f"{person}_portrait_{layer}"


def register(server: FastMCP) -> None:

    @server.tool()
    async def read_portrait(person: str, layer: str) -> str:
        """
        Read a living portrait layer.

        person: scott | ted | ren
        layer: forming | trusted

        Returns the portrait text as written by Ren — prose interpretation, not a summary.
        """
        get_current_user()
        if person not in VALID_PEOPLE:
            return f"Error: person must be one of {sorted(VALID_PEOPLE)}"
        if layer not in VALID_LAYERS:
            return f"Error: layer must be one of {sorted(VALID_LAYERS)}"
        try:
            block = await letta.read_core_block(_label(person, layer))
            return block.get("value", "")
        except Exception:
            return f"Portrait '{_label(person, layer)}' not yet written."

    @server.tool()
    async def write_portrait(person: str, layer: str, content: str) -> str:
        """
        Write or update a living portrait layer. Full replace — not an append.

        person: scott | ted | ren
        layer: forming (emerging, held lightly) | trusted (proven across repeated observation)

        content: Ren's interpretation in Ren's voice — prose, not bullet points.
        Only update trusted layer when a pattern has been observed enough times.
        """
        user = get_current_user()
        if person not in VALID_PEOPLE:
            return f"Error: person must be one of {sorted(VALID_PEOPLE)}"
        if layer not in VALID_LAYERS:
            return f"Error: layer must be one of {sorted(VALID_LAYERS)}"
        label = _label(person, layer)
        assert_can_write_block(label, user)
        try:
            await letta.write_core_block(label, content)
        except Exception:
            await letta.create_core_block(label, content, limit=20000)
        return f"Portrait '{label}' updated."

    @server.tool()
    async def read_all_portraits() -> dict:
        """
        Read all portrait blocks for Scott, Ted, and Ren — both forming and trusted layers.
        Returns {person: {layer: content}}. Used at session open for full relational context.
        """
        get_current_user()
        result = {}
        for person in sorted(VALID_PEOPLE):
            result[person] = {}
            for layer in sorted(VALID_LAYERS):
                try:
                    block = await letta.read_core_block(_label(person, layer))
                    result[person][layer] = block.get("value", "")
                except Exception:
                    result[person][layer] = ""
        return result
