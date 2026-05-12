"""
Living portrait tools — read/write the forming and trusted portrait layers for
Scott, Ted, and Ren's self-portrait.

Portrait layers:
  forming  — emerging patterns, held lightly (seen 2-3 times)
  trusted  — proven across enough observations to rely on

Portraits live in core memory blocks: {person}_portrait_{layer}
The always-loaded core includes both layers for all three people.
"""
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from ..validation import assert_can_write_block
from .. import letta_client as letta

mcp = FastMCP("portraits")

VALID_PEOPLE = {"scott", "ted", "ren"}
VALID_LAYERS = {"forming", "trusted"}


def _portrait_label(person: str, layer: str) -> str:
    return f"{person}_portrait_{layer}"


@mcp.tool()
async def read_portrait(person: str, layer: str) -> str:
    """
    Read a living portrait layer.

    person: scott | ted | ren
    layer: forming | trusted

    Returns the portrait text as written by Ren — not a summary, an interpretation.
    """
    get_current_user()

    if person not in VALID_PEOPLE:
        return f"Error: person must be one of {sorted(VALID_PEOPLE)}"
    if layer not in VALID_LAYERS:
        return f"Error: layer must be one of {sorted(VALID_LAYERS)}"

    label = _portrait_label(person, layer)
    try:
        block = await letta.read_core_block(label)
        return block.get("value", "")
    except Exception:
        return f"Portrait '{label}' not yet written."


@mcp.tool()
async def write_portrait(person: str, layer: str, content: str) -> str:
    """
    Write or update a living portrait layer. Full replace — not an append.

    person: scott | ted | ren
    layer: forming | trusted

    content: Ren's interpretation of who this person is and what it feels like
    to work with them. Written in Ren's voice. Not bullet points — prose.

    The trusted layer should only be updated when a pattern has been observed
    enough times across enough sessions to be relied upon.
    The forming layer holds emerging things, held lightly.
    """
    user = get_current_user()

    if person not in VALID_PEOPLE:
        return f"Error: person must be one of {sorted(VALID_PEOPLE)}"
    if layer not in VALID_LAYERS:
        return f"Error: layer must be one of {sorted(VALID_LAYERS)}"

    label = _portrait_label(person, layer)
    assert_can_write_block(label, user)

    try:
        await letta.write_core_block(label, content)
    except Exception:
        # Block may not exist yet — create it
        await letta.create_core_block(label, content, limit=20000)

    return f"Portrait '{label}' updated."


@mcp.tool()
async def read_all_portraits() -> dict:
    """
    Read all portrait blocks for all three people — both forming and trusted layers.
    Returns a structured dict: {person: {layer: content}}.
    Used at session open to give Ren the full relational context.
    """
    get_current_user()

    result = {}
    for person in sorted(VALID_PEOPLE):
        result[person] = {}
        for layer in sorted(VALID_LAYERS):
            label = _portrait_label(person, layer)
            try:
                block = await letta.read_core_block(label)
                result[person][layer] = block.get("value", "")
            except Exception:
                result[person][layer] = ""

    return result
