"""
Core memory tools — read/write named memory blocks (Store 4 always-loaded core).
"""
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from ..validation import assert_can_write_block
from .. import letta_client as letta
from .. import db


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

    @server.tool()
    async def log_memory_access(
        search_query: str,
        passage_ids: list[str],
        used_in_response: bool,
    ) -> str:
        """
        Log an archival memory search for access pattern analysis (the MRI).

        Call this after EVERY archival_memory_search, without exception:
        - search_query: the exact string you searched for
        - passage_ids: list of passage IDs returned (empty list if nothing found)
        - used_in_response: True if you actually used the results in your reply, False if not

        This builds the access log that identifies cold passages (never surfacing),
        dry wells (searches that always fail), and false positives (found but unused).
        It is the feedback loop that makes the memory system self-improving over time.
        """
        get_current_user()
        session_id = await letta.ensure_ren_agent_id()
        ok = await db.log_memory_access(
            search_query=search_query,
            passage_ids=passage_ids or [],
            used_in_response=used_in_response,
            session_id=session_id,
        )
        if ok:
            found = len(passage_ids or [])
            return f"Logged: query='{search_query[:40]}', {found} result(s), used={used_in_response}."
        return "Log write failed — continuing."

    @server.tool()
    async def delete_archival_passage(passage_id: str, confirmed: bool = False) -> str:
        """
        Delete an archival memory passage with a two-step approval flow.

        confirmed=False (default): returns the passage ID and a confirmation prompt.
        Only call with confirmed=True after Scott explicitly approves the deletion.

        passage_id: the Letta passage ID (UUID from archival_memory_search results)

        Use this to remove duplicate, stale, or incorrect passages from archival memory.
        Deletions are permanent — there is no undo.
        """
        get_current_user()
        # No content preview on confirmed=False: Letta has no single-passage GET endpoint,
        # and Ren already has the content from the archival_memory_search that surfaced the ID.
        # The two-step guard here is purely against accidental calls, not a content review.
        if not confirmed:
            return (
                f"Passage {passage_id} flagged for deletion — awaiting Scott's approval.\n"
                f"Call delete_archival_passage('{passage_id}', confirmed=True) to permanently delete."
            )
        await letta.delete_passage(passage_id)
        return f"Passage {passage_id} permanently deleted from archival memory."

    @server.tool()
    async def update_open_threads(action: str, thread: str) -> str:
        """
        Add, close, or remove an item from Ren's open threads list (a Letta core block).

        action: 'add' | 'close' | 'remove'
        thread: the thread text to act on

        'add'    — appends a new thread to the list
        'close'  — marks the matching thread as [CLOSED]
        'remove' — deletes the matching thread from the list entirely

        Matching for 'close' and 'remove' is case-insensitive substring match.
        If the open_threads block does not exist, 'add' creates it.
        """
        get_current_user()

        if action not in ("add", "close", "remove"):
            return "Error: action must be 'add', 'close', or 'remove'"
        if not thread.strip():
            return "Error: thread is required"

        t = thread.strip()
        block = await letta.read_core_block("open_threads")
        # Block may not exist yet — start with empty list
        raw = block.get("value", "") if block else ""
        lines = [l for l in raw.splitlines() if l.strip()]

        if action == "add":
            lines.append(f"- {t}")
        elif action == "close":
            # Find matching line (case-insensitive substring) and prefix with [CLOSED]
            matched = False
            for i, line in enumerate(lines):
                if t.lower() in line.lower() and "[CLOSED]" not in line:
                    lines[i] = line.replace("- ", "- [CLOSED] ", 1) if line.startswith("- ") else f"- [CLOSED] {line.lstrip('- ')}"
                    matched = True
                    break
            if not matched:
                return f"No open thread matching '{t}' found"
        elif action == "remove":
            before = len(lines)
            lines = [l for l in lines if t.lower() not in l.lower()]
            if len(lines) == before:
                return f"No thread matching '{t}' found"

        updated = "\n".join(lines)
        try:
            await letta.write_core_block("open_threads", updated)
        except Exception:
            await letta.create_core_block("open_threads", updated, limit=10000)

        count = len([l for l in lines if l.strip() and "[CLOSED]" not in l])
        return f"Open threads updated — action={action}, {count} open thread(s) remaining."

    @server.tool()
    async def enrich_passage(passage_id: str, context_note: str, session_date: str = "") -> str:
        """
        Record context about how a passage was used during retrieval (memory reconsolidation).

        Call this when an archival passage was meaningfully retrieved and used in a response.
        The context note accumulates over time — each note is appended, never overwritten.
        Future retrievals of this passage will include these notes as additional context.

        passage_id: the Letta passage ID (from archival_memory_search results)
        context_note: what this passage was used for, what session context it connected to
        session_date: YYYY-MM-DD (optional, defaults to today)
        """
        get_current_user()
        ok = await db.write_passage_enrichment(passage_id, context_note, session_date or None)
        if ok:
            return f"Enrichment recorded for passage {passage_id[:8]}."
        return f"Failed to record enrichment for passage {passage_id[:8]}."
