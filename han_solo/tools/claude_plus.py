"""
Claude Plus tools — fetch all 10 persistent blocks for Claude Plus session activation.
"""
import json

from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import db


def register(server: FastMCP) -> None:

    @server.tool()
    async def get_claude_plus_blocks() -> dict:
        """
        Fetch all 10 Claude Plus blocks from Han Solo DB for session activation.

        Returns each block's content and metadata. Claude Plus calls this at
        session start to load its operating context, state machine, and pending work.

        Blocks returned:
        - identity_and_role
        - operating_contract
        - hub_snapshot
        - session_shape
        - slice_sizing_log
        - state_machine (current session state)
        - session_close (last close procedure status)
        - pending_decisions (open items only)
        - failure_recovery
        - framework_state
        """
        get_current_user()

        pool = db._pool
        if not pool:
            return {"error": "DB pool not available"}

        async with pool.acquire() as conn:
            identity_row = await conn.fetchrow(
                "SELECT content, updated_at, updated_by FROM claude_plus_identity_and_role ORDER BY updated_at DESC LIMIT 1"
            )
            contract_row = await conn.fetchrow(
                "SELECT content, updated_at, updated_by FROM claude_plus_operating_contract ORDER BY updated_at DESC LIMIT 1"
            )
            hub_row = await conn.fetchrow(
                "SELECT hub_data, hub_schema_version, snapshot_at FROM hub_snapshot_current ORDER BY updated_at DESC LIMIT 1"
            )
            shape_row = await conn.fetchrow(
                "SELECT slices_completed, slices_in_progress, context_consumption_estimate, session_mode, notes, updated_at FROM session_shape_and_boundaries ORDER BY updated_at DESC LIMIT 1"
            )
            sizing_row = await conn.fetchrow(
                "SELECT recent_decisions, updated_at FROM slice_sizing_decision_log ORDER BY updated_at DESC LIMIT 1"
            )
            state_row = await conn.fetchrow(
                "SELECT hub_read, code_read_current_slice, gate_entry_written, scott_approved, session_mode, pending_decisions_count, close_signal_fired, session_close_confirmed, updated_at FROM claude_plus_state_machine ORDER BY updated_at DESC LIMIT 1"
            )
            close_row = await conn.fetchrow(
                "SELECT triggers_fired, close_procedure_status, updated_at FROM session_close ORDER BY updated_at DESC LIMIT 1"
            )
            pending_rows = await conn.fetch(
                "SELECT id::text, description, flagged_at, owner, status FROM pending_actions_and_decisions WHERE status = 'open' ORDER BY flagged_at ASC"
            )
            recovery_row = await conn.fetchrow(
                "SELECT content, updated_at FROM failure_recovery_procedures ORDER BY updated_at DESC LIMIT 1"
            )
            framework_row = await conn.fetchrow(
                "SELECT version, status, active_skills, north_stars, recent_decisions, open_curator_work, updated_at FROM framework_state ORDER BY updated_at DESC LIMIT 1"
            )

        def _ts(row, key):
            val = row[key] if row and row[key] else None
            return val.isoformat() if val else None

        return {
            "identity_and_role": {
                "content": identity_row["content"] if identity_row else "",
                "updated_at": _ts(identity_row, "updated_at") if identity_row else None,
                "updated_by": identity_row["updated_by"] if identity_row else None,
            },
            "operating_contract": {
                "content": contract_row["content"] if contract_row else "",
                "updated_at": _ts(contract_row, "updated_at") if contract_row else None,
                "updated_by": contract_row["updated_by"] if contract_row else None,
            },
            "hub_snapshot": {
                "hub_data": json.loads(hub_row["hub_data"]) if hub_row and hub_row["hub_data"] else {},
                "schema_version": hub_row["hub_schema_version"] if hub_row else None,
                "snapshot_at": _ts(hub_row, "snapshot_at") if hub_row else None,
            },
            "session_shape": {
                "slices_completed": shape_row["slices_completed"] if shape_row else 0,
                "slices_in_progress": shape_row["slices_in_progress"] if shape_row else 0,
                "context_estimate": shape_row["context_consumption_estimate"] if shape_row else "light",
                "session_mode": shape_row["session_mode"] if shape_row else "sprint",
                "notes": shape_row["notes"] if shape_row else "",
                "updated_at": _ts(shape_row, "updated_at") if shape_row else None,
            },
            "slice_sizing_log": {
                "recent_decisions": json.loads(sizing_row["recent_decisions"]) if sizing_row and sizing_row["recent_decisions"] else [],
                "updated_at": _ts(sizing_row, "updated_at") if sizing_row else None,
            },
            "state_machine": {
                "hub_read": state_row["hub_read"] if state_row else False,
                "code_read_current_slice": state_row["code_read_current_slice"] if state_row else "n/a",
                "gate_entry_written": state_row["gate_entry_written"] if state_row else False,
                "scott_approved": state_row["scott_approved"] if state_row else False,
                "session_mode": state_row["session_mode"] if state_row else "sprint",
                "pending_decisions_count": state_row["pending_decisions_count"] if state_row else 0,
                "close_signal_fired": state_row["close_signal_fired"] if state_row else False,
                "session_close_confirmed": state_row["session_close_confirmed"] if state_row else False,
                "updated_at": _ts(state_row, "updated_at") if state_row else None,
            },
            "session_close": {
                "triggers_fired": json.loads(close_row["triggers_fired"]) if close_row and close_row["triggers_fired"] else [],
                "close_procedure_status": json.loads(close_row["close_procedure_status"]) if close_row and close_row["close_procedure_status"] else {},
                "updated_at": _ts(close_row, "updated_at") if close_row else None,
            },
            "pending_decisions": [
                {
                    "id": row["id"],
                    "description": row["description"],
                    "flagged_at": row["flagged_at"].isoformat() if row["flagged_at"] else None,
                    "owner": row["owner"],
                    "status": row["status"],
                }
                for row in pending_rows
            ],
            "failure_recovery": {
                "content": recovery_row["content"] if recovery_row else "",
                "updated_at": _ts(recovery_row, "updated_at") if recovery_row else None,
            },
            "framework_state": {
                "version": framework_row["version"] if framework_row else "",
                "status": framework_row["status"] if framework_row else "",
                "active_skills": json.loads(framework_row["active_skills"]) if framework_row and framework_row["active_skills"] else [],
                "north_stars": framework_row["north_stars"] if framework_row else "",
                "recent_decisions": json.loads(framework_row["recent_decisions"]) if framework_row and framework_row["recent_decisions"] else [],
                "open_curator_work": framework_row["open_curator_work"] if framework_row else "",
                "updated_at": _ts(framework_row, "updated_at") if framework_row else None,
            },
        }
