"""
Notecard tools — low-ceremony captures created by Scott, Ren, or Ted mid-session.

A notecard is not a task and not a thread. No state machine, no assignee.
Just text + who wrote it + when + where it came from.

Statuses: active | completed | archived
"""
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import db
from .. import letta_client as letta

VALID_STATUSES = {"active", "completed", "archived", "pending_deletion"}


def register(server: FastMCP) -> None:

    @server.tool()
    async def create_notecard(text: str, source: str = "chat") -> str:
        """
        Create a notecard. Use this when something comes up mid-session that's
        worth capturing — a follow-up, a reminder, a thing to revisit. Not a task.

        text: the notecard content
        source: 'chat' (mid-session) | 'manual' (created outside of chat)
        """
        user = get_current_user()
        session_id = await letta.ensure_ren_agent_id()
        result = await db.create_notecard(
            text=text,
            creator=user.id,
            source=source,
            session_id=session_id,
        )
        if not result:
            return "Error: failed to create notecard"
        return f"Notecard created — id={result['id']}, creator={user.name}"

    @server.tool()
    async def update_notecard(notecard_id: int, status: str = "", text: str = "") -> str:
        """
        Update a notecard's status and/or text.

        notecard_id: the id of the notecard to update
        status: 'active' | 'completed' | 'archived' | '' (leave blank to keep current)
        text: new text content | '' (leave blank to keep current)

        Use this to mark a notecard complete when the item has been addressed,
        archive it when it's no longer relevant, or correct its text.
        """
        get_current_user()
        s = status.strip() or None
        t = text.strip() or None
        if s is not None and s not in VALID_STATUSES:
            return f"Error: status must be one of {sorted(VALID_STATUSES)}"
        if s is None and t is None:
            return "Error: provide status or text to update"
        ok = await db.update_notecard(notecard_id, status=s, text=t)
        if not ok:
            return f"Error: notecard {notecard_id} not found or update failed"
        parts = []
        if s: parts.append(f"status={s}")
        if t: parts.append(f"text updated")
        return f"Notecard {notecard_id} updated — {', '.join(parts)}"

    @server.tool()
    async def delete_notecard(notecard_id: int, confirmed: bool = False) -> str:
        """
        Delete a notecard with a two-step approval flow.

        confirmed=False (default): marks the notecard as pending_deletion and returns
        its content for Scott to review. Call again with confirmed=True to permanently delete.

        confirmed=True: permanently deletes the notecard. Only call after Scott approves.
        """
        get_current_user()
        card = await db.get_notecard(notecard_id)
        if not card:
            return f"Error: notecard {notecard_id} not found"
        if not confirmed:
            ok = await db.update_notecard(notecard_id, status="pending_deletion")
            if not ok:
                return f"Error: failed to mark notecard {notecard_id} for deletion"
            return (
                f"Notecard {notecard_id} marked for deletion — awaiting Scott's approval.\n"
                f"Content: {card['text']}\n"
                f"Call delete_notecard({notecard_id}, confirmed=True) to permanently delete."
            )
        ok = await db.delete_notecard(notecard_id)
        if not ok:
            return f"Error: failed to delete notecard {notecard_id}"
        return f"Notecard {notecard_id} permanently deleted."

    @server.tool()
    async def list_notecards(status: str = "") -> list[dict]:
        """
        List notecards.

        status: 'active' | 'completed' | 'archived' | '' (returns active + completed)

        Returns id, text, creator, status, source, session_id, created_at for each.
        """
        get_current_user()
        valid = {"active", "completed", "archived", ""}
        if status not in valid:
            return [{"error": f"status must be one of {sorted(valid)}"}]
        cards = await db.list_notecards(status=status or None)
        return [
            {
                "id": c["id"],
                "text": c["text"],
                "creator": c["creator"],
                "status": c["status"],
                "source": c["source"],
                "session_id": c.get("session_id"),
                "created_at": c["created_at"].isoformat() if c.get("created_at") else None,
            }
            for c in cards
        ]
