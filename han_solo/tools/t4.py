"""
T4 project memory tools — write, retrieve, and search framework artifacts
produced across the Solo Builder Framework build cycle.

Entry types and write behaviors:
  write_once : tech_context, data_mapping, design_identity, sprint_screen,
               research_gaps
  upsert     : phase, deliverable, slice, deferred_decisions, handoff,
               current_phase, metrics, retro
  append     : discovery_brief, brainstorm, as_is_map, to_be_map,
               decisions_log
"""
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import db

# Derive write behavior from entry type — caller never specifies this directly
WRITE_BEHAVIORS: dict[str, str] = {
    "phase":              "upsert",
    "deliverable":        "upsert",
    "slice":              "upsert",
    "discovery_brief":    "append",
    "brainstorm":         "append",
    "tech_context":       "write_once",
    "data_mapping":       "write_once",
    "design_identity":    "write_once",
    "as_is_map":          "append",
    "to_be_map":          "append",
    "sprint_screen":      "write_once",
    "research_gaps":      "write_once",
    "deferred_decisions": "upsert",
    "handoff":            "upsert",
    "decisions_log":      "append",
    "current_phase":      "upsert",
    "metrics":            "upsert",
    "retro":              "write_once",
}

# Entry types where entry_id is auto-set to the type name
AUTO_ID_TYPES = {
    "discovery_brief", "brainstorm", "tech_context", "data_mapping",
    "design_identity", "as_is_map", "to_be_map", "research_gaps",
    "deferred_decisions", "handoff", "decisions_log", "current_phase",
    "metrics",
}

# Hierarchy entry types that require plain_language + technical_description
TYPED_ENTRIES = {"phase", "deliverable", "slice"}


def _format_typed_content(
    entry_type: str,
    entry_id: str,
    plain_language: str,
    technical_description: str,
    status: str,
    acceptance_criteria: list[str] | None,
    anchor_design: str | None,
    anchor_data: str | None,
    anchor_done: str | None,
    anchor_process: str | None,
    done_criteria: list[str] | None,
    quality_contract: str | None,
    dependencies: list[str] | None,
) -> str:
    lines = [
        f"# {entry_type.upper()} — {entry_id}",
        f"**Status:** {status or 'Defined'}",
        "",
        "## Plain language",
        plain_language,
        "",
        "## Technical description",
        technical_description,
    ]
    if acceptance_criteria:
        lines += ["", "## Acceptance criteria"]
        lines += [f"- {c}" for c in acceptance_criteria]
    if entry_type == "slice":
        if anchor_design or anchor_data or anchor_done or anchor_process:
            lines += ["", "## Anchors"]
            if anchor_design:
                lines.append(f"**Design:** {anchor_design}")
            if anchor_data:
                lines.append(f"**Data:** {anchor_data}")
            if anchor_done:
                lines.append(f"**Done:** {anchor_done}")
            if anchor_process:
                lines.append(f"**Process:** {anchor_process}")
        if done_criteria:
            lines += ["", "## Done criteria"]
            lines += [f"- {c}" for c in done_criteria]
        if quality_contract:
            lines += ["", "## Quality contract", quality_contract]
        if dependencies:
            lines += ["", "## Dependencies"]
            lines += [f"- {d}" for d in dependencies]
    return "\n".join(lines)


def register(server: FastMCP) -> None:

    @server.tool()
    async def write_t4_entry(
        project_slug: str,
        entry_type: str,
        content: str = "",
        entry_id: str = "",
        parent_id: str = "",
        plain_language: str = "",
        technical_description: str = "",
        status: str = "",
        acceptance_criteria: list[str] | None = None,
        anchor_design: str = "",
        anchor_data: str = "",
        anchor_done: str = "",
        anchor_process: str = "",
        done_criteria: list[str] | None = None,
        quality_contract: str = "",
        dependencies: list[str] | None = None,
    ) -> str:
        """
        Write a T4 project memory artifact to Han Solo.

        project_slug: kebab-case project name e.g. "fantasy-football"
        entry_type: phase | deliverable | slice | discovery_brief | brainstorm |
                    tech_context | data_mapping | design_identity | as_is_map |
                    to_be_map | sprint_screen | research_gaps | deferred_decisions |
                    handoff | decisions_log | current_phase | metrics | retro
        content: free-form markdown (structural artifact types)
        entry_id: required for phase/deliverable/slice/sprint_screen/retro; auto-set for others
        parent_id: deliverable ID for slices; phase ID for deliverables
        plain_language: required for phase/deliverable/slice
        technical_description: required for phase/deliverable/slice
        status: current status (hierarchy entries)
        acceptance_criteria: list of criteria strings (phase/deliverable)
        anchor_design/data/done/process: four anchors (slice only)
        done_criteria: verifiable done statements (slice only)
        quality_contract: non-functional requirements (slice only)
        dependencies: list of dependency strings (slice only)
        """
        get_current_user()

        # Ensure project record exists (idempotent — creates only if missing)
        await db.ensure_project_exists(project_slug)

        if entry_type not in WRITE_BEHAVIORS:
            return f"Error: unknown entry_type '{entry_type}'. Valid types: {sorted(WRITE_BEHAVIORS)}"

        # Resolve entry_id
        resolved_id = entry_id if entry_id else (entry_type if entry_type in AUTO_ID_TYPES else "")
        if not resolved_id:
            return f"Error: entry_id is required for {entry_type}"

        # Validate and build content for typed hierarchy entries
        if entry_type in TYPED_ENTRIES:
            if not plain_language:
                return f"Error: plain_language is required for {entry_type}"
            if not technical_description:
                return f"Error: technical_description is required for {entry_type}"
            resolved_content = _format_typed_content(
                entry_type=entry_type,
                entry_id=resolved_id,
                plain_language=plain_language,
                technical_description=technical_description,
                status=status,
                acceptance_criteria=acceptance_criteria,
                anchor_design=anchor_design or None,
                anchor_data=anchor_data or None,
                anchor_done=anchor_done or None,
                anchor_process=anchor_process or None,
                done_criteria=done_criteria,
                quality_contract=quality_contract or None,
                dependencies=dependencies,
            )
        else:
            if not content:
                return f"Error: content is required for {entry_type}"
            resolved_content = content

        behavior = WRITE_BEHAVIORS[entry_type]
        result = await db.write_t4_entry(
            project_slug=project_slug,
            entry_type=entry_type,
            entry_id=resolved_id,
            content=resolved_content,
            parent_id=parent_id or None,
            behavior=behavior,
        )

        if "error" in result:
            return f"Error: {result['error']}"
        return f"T4 entry written — {entry_type}/{resolved_id} for {project_slug} [{behavior}]"

    @server.tool()
    async def get_t4_entry(
        project_slug: str,
        entry_type: str,
        entry_id: str = "",
    ) -> dict:
        """
        Fetch a T4 artifact by project, type, and ID.

        project_slug: kebab-case project name
        entry_type: the artifact type
        entry_id: omit for auto-ID types (discovery_brief, tech_context, etc.)

        Returns the full entry content or an error dict if not found.
        """
        get_current_user()

        if entry_type not in WRITE_BEHAVIORS:
            return {"error": f"unknown entry_type '{entry_type}'"}

        resolved_id = entry_id if entry_id else (entry_type if entry_type in AUTO_ID_TYPES else "")
        if not resolved_id:
            return {"error": f"entry_id is required for {entry_type}"}

        row = await db.get_t4_entry(
            project_slug=project_slug,
            entry_type=entry_type,
            entry_id=resolved_id,
        )
        if not row:
            return {"error": f"No T4 entry found: {project_slug}/{entry_type}/{resolved_id}"}

        return {
            "id": row["id"],
            "project_slug": row["project_slug"],
            "entry_type": row["entry_type"],
            "entry_id": row["entry_id"],
            "parent_id": row.get("parent_id"),
            "content": row["content"],
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        }

    @server.tool()
    async def search_t4(
        project_slug: str,
        query: str,
        entry_type: str = "",
        limit: int = 10,
    ) -> list[dict]:
        """
        Search T4 artifacts for a project by keyword.

        project_slug: kebab-case project name
        query: keyword or phrase to search in content
        entry_type: optional filter to a specific artifact type
        limit: max results (default 10)

        Returns matching entries with id, entry_type, entry_id, content excerpt, updated_at.
        """
        get_current_user()

        rows = await db.search_t4(
            project_slug=project_slug,
            query=query,
            entry_type=entry_type or None,
            limit=limit,
        )
        results = []
        for r in rows:
            content = r["content"]
            excerpt = content[:300] + "..." if len(content) > 300 else content
            results.append({
                "id": r["id"],
                "entry_type": r["entry_type"],
                "entry_id": r["entry_id"],
                "parent_id": r.get("parent_id"),
                "excerpt": excerpt,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
            })
        return results

    @server.tool()
    async def delete_t4_entry(
        project_slug: str,
        entry_type: str,
        entry_id: str = "",
    ) -> dict:
        """
        Delete a T4 entry by project, type, and ID.

        project_slug: kebab-case project name
        entry_type: the artifact type
        entry_id: omit to delete ALL entries of this type for the project

        Returns count of deleted rows.
        """
        get_current_user()

        if entry_type not in WRITE_BEHAVIORS:
            return {"error": f"unknown entry_type '{entry_type}'"}

        result = await db.delete_t4_entry(
            project_slug=project_slug,
            entry_type=entry_type,
            entry_id=entry_id or None,
        )
        if "error" in result:
            return {"error": result["error"]}
        return {"deleted": result["deleted"], "project_slug": project_slug, "entry_type": entry_type, "entry_id": entry_id or "(all)"}
