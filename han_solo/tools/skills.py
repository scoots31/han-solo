"""
Framework skill tools — read phase skill content from the skills table (Store 1).

The skills table is the authoritative source of Solo Builder Framework skill content.
It is populated by the sync pipeline and injected into Claude Code sessions
via the framework-skill-inject hook on every UserPromptSubmit.

Ren uses these tools to understand what phase Claude Code is currently operating in
and what guidance that phase provides — closing the gap between how Claude Code
experiences the framework and how Ren understands the work in progress.
"""
from mcp.server.fastmcp import FastMCP

from ..auth import get_current_user
from .. import db


def register(server: FastMCP) -> None:

    @server.tool()
    async def get_skill(phase_slug: str) -> dict:
        """
        Read the content of a framework phase skill by slug.

        Use this to understand what phase Claude Code is currently operating in
        and what guidance, gate logic, and outputs that phase defines.

        Common phase slugs:
          discover, tech-context, design-sprint, design-review, prd-to-plan,
          to-issues, solo-build, solo-qa, deploy, brainstorming, start,
          data-scaffold, phase-test, autopilot

        Returns: {phase_slug, layer, content, updated_at} or an error dict.
        """
        get_current_user()

        row = await db.get_skill(phase_slug)
        if not row:
            return {"error": f"No skill found for slug '{phase_slug}'. Use list_skills to see available slugs."}

        return {
            "phase_slug": row["phase_slug"],
            "layer": row["layer"],
            "content": row["content"],
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        }

    @server.tool()
    async def list_skills() -> list[dict]:
        """
        List all framework phase skills currently stored in Han Solo.

        Returns each skill's slug, layer, content length (chars), and last update.
        Use this to discover what skills are available before calling get_skill.
        """
        get_current_user()

        rows = await db.list_skills()
        return [
            {
                "phase_slug": r["phase_slug"],
                "layer": r["layer"],
                "chars": len(r.get("content", "")),
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
            }
            for r in rows
        ]
