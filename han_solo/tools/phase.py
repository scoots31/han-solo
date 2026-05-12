"""
Phase gate tools — read project state and check phase transition prerequisites.
Project state lives in the 'project_state' core memory block as JSON.
"""
import json
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import letta_client as letta

PHASE_PREREQUISITES: dict[str, list[str]] = {
    "discover": [],
    "tech_context": ["brainstorm_artifact"],
    "shape": ["discovery_artifact"],
    "prd_to_plan": ["shape_document"],
    "build_slice_1": ["backlog", "selected_slice"],
    "build_next": ["previous_slice_qa_cleared"],
    "deploy": ["all_slices_cleared", "phase_test_passed"],
}


async def _load_state() -> dict:
    try:
        block = await letta.read_core_block("project_state")
        return json.loads(block.get("value", "{}"))
    except Exception:
        return {}


async def _save_state(state: dict) -> None:
    await letta.write_core_block("project_state", json.dumps(state, indent=2))


def register(server: FastMCP) -> None:

    @server.tool()
    async def get_project_state() -> dict:
        """
        Read current project state: active phase, completed gates, artifact inventory,
        current slice, and any open amendments. Source of truth for phase awareness.
        """
        get_current_user()
        return await _load_state()

    @server.tool()
    async def check_phase_gate(target_phase: str) -> dict:
        """
        Check whether a transition to target_phase is currently allowed.

        Returns allowed (bool), reason (why blocked), and missing prerequisites.

        target_phase: discover | tech_context | shape | prd_to_plan |
                      build_slice_1 | build_next | deploy
        """
        get_current_user()
        if target_phase not in PHASE_PREREQUISITES:
            return {"allowed": False, "reason": f"Unknown phase '{target_phase}'", "missing": []}
        state = await _load_state()
        artifacts = state.get("artifacts", {})
        missing = [p for p in PHASE_PREREQUISITES[target_phase] if not artifacts.get(p)]
        if missing:
            return {"allowed": False, "reason": f"Prerequisites not satisfied for '{target_phase}'", "missing": missing}
        return {"allowed": True, "reason": "", "missing": []}

    @server.tool()
    async def advance_phase(target_phase: str) -> str:
        """
        Advance project state to target_phase. Blocked if gate prerequisites are unmet.
        """
        user = get_current_user()
        gate = await check_phase_gate(target_phase)
        if not gate["allowed"]:
            return f"BLOCKED: {gate['reason']}. Missing: {gate['missing']}"
        state = await _load_state()
        state["current_phase"] = target_phase
        state.setdefault("phase_history", []).append({
            "phase": target_phase,
            "entered_by": user.id,
            "at": datetime.utcnow().isoformat(),
        })
        await _save_state(state)
        return f"Phase advanced to '{target_phase}'."

    @server.tool()
    async def record_artifact(artifact_key: str, description: str) -> str:
        """
        Record that a phase artifact exists, unlocking downstream phase gates.

        artifact_key: e.g. brainstorm_artifact, backlog, shape_document,
                      previous_slice_qa_cleared
        description: short description of what was produced
        """
        user = get_current_user()
        state = await _load_state()
        state.setdefault("artifacts", {})[artifact_key] = {
            "description": description,
            "recorded_by": user.id,
        }
        await _save_state(state)
        return f"Artifact '{artifact_key}' recorded."
