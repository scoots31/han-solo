"""
Phase gate tools — read project state and check phase transition prerequisites.
Project state lives in the 'project_state' core memory block as JSON.

Phase gate checks (from design):
  discover:       brainstorm artifact OR direct brief exists
  tech_context:   discovery artifact exists
  shape:          project profile exists
  prd_to_plan:    shape document exists
  build_slice_1:  backlog exists, slice selected
  build_next:     previous slice QA cleared
  deploy:         all slices cleared, phase test passed
"""
import json

from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import letta_client as letta

mcp = FastMCP("phase")

# Ordered phase list — each phase declares what the previous phase must have produced
PHASE_PREREQUISITES: dict[str, list[str]] = {
    "discover": [],
    "tech_context": ["brainstorm_artifact"],
    "shape": ["discovery_artifact"],
    "prd_to_plan": ["shape_document"],
    "build_slice_1": ["backlog", "selected_slice"],
    "build_next": ["previous_slice_qa_cleared"],
    "deploy": ["all_slices_cleared", "phase_test_passed"],
}


async def _load_project_state() -> dict:
    try:
        block = await letta.read_core_block("project_state")
        return json.loads(block.get("value", "{}"))
    except Exception:
        return {}


async def _save_project_state(state: dict) -> None:
    await letta.write_core_block("project_state", json.dumps(state, indent=2))


@mcp.tool()
async def get_project_state() -> dict:
    """
    Read the current project state: active phase, completed gates, artifact inventory,
    current slice, and any open amendments.

    This is the source of truth for phase awareness — assembled context reads this
    before deciding what to pass to Claude.
    """
    get_current_user()
    return await _load_project_state()


@mcp.tool()
async def check_phase_gate(target_phase: str) -> dict:
    """
    Check whether a transition to target_phase is currently allowed.

    Returns:
      allowed: bool
      reason: why it's blocked (if not allowed)
      missing: list of prerequisites not yet satisfied

    target_phase: discover | tech_context | shape | prd_to_plan |
                  build_slice_1 | build_next | deploy
    """
    get_current_user()

    if target_phase not in PHASE_PREREQUISITES:
        return {
            "allowed": False,
            "reason": f"Unknown phase '{target_phase}'",
            "missing": [],
        }

    state = await _load_project_state()
    artifacts = state.get("artifacts", {})

    missing = [
        prereq
        for prereq in PHASE_PREREQUISITES[target_phase]
        if not artifacts.get(prereq)
    ]

    if missing:
        return {
            "allowed": False,
            "reason": f"Prerequisites not satisfied for '{target_phase}'",
            "missing": missing,
        }

    return {"allowed": True, "reason": "", "missing": []}


@mcp.tool()
async def advance_phase(target_phase: str) -> str:
    """
    Advance project state to target_phase after confirming the gate is clear.
    Records the phase transition with a timestamp.

    Only allowed if check_phase_gate returns allowed=True.
    """
    user = get_current_user()

    gate = await check_phase_gate(target_phase)
    if not gate["allowed"]:
        return f"BLOCKED: {gate['reason']}. Missing: {gate['missing']}"

    state = await _load_project_state()
    from datetime import datetime
    state["current_phase"] = target_phase
    state.setdefault("phase_history", []).append({
        "phase": target_phase,
        "entered_by": user.id,
        "at": datetime.utcnow().isoformat(),
    })
    await _save_project_state(state)
    return f"Phase advanced to '{target_phase}'."


@mcp.tool()
async def record_artifact(artifact_key: str, description: str) -> str:
    """
    Record that a phase artifact exists, unlocking downstream phase gates.

    artifact_key: the prerequisite key (e.g. brainstorm_artifact, backlog,
                  shape_document, previous_slice_qa_cleared)
    description: short description of what was produced

    This is how phase gates get cleared — record the artifact, then the gate opens.
    """
    user = get_current_user()
    state = await _load_project_state()
    state.setdefault("artifacts", {})[artifact_key] = {
        "description": description,
        "recorded_by": user.id,
    }
    await _save_project_state(state)
    return f"Artifact '{artifact_key}' recorded."
