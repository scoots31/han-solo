#!/usr/bin/env python3
"""
seed_skills.py — Populate the skills table from engineering-playbook SKILL.md files.

Run manually whenever skill content changes:
    DATABASE_URL=... python3 scripts/seed_skills.py

Phase skills are seeded as layer=phase-active.
The always-on content is managed separately via ~/.claude/hooks/framework-always-on.md
and is not stored in the skills table.
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "")

PLAYBOOK = Path.home() / "Developer" / "engineering-playbook" / "skills"

# Map skill folder name -> phase slug used by the hook
PHASE_SKILLS = [
    "brainstorming",
    "discover",
    "tech-context",
    "design-sprint",
    "data-scaffold",
    "design-review",
    "prd-to-plan",
    "to-issues",
    "solo-build",
    "autopilot",
    "solo-qa",
    "phase-test",
    "deploy",
]


async def seed():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)

    seeded = 0
    skipped = 0

    for phase_slug in PHASE_SKILLS:
        skill_file = PLAYBOOK / phase_slug / "SKILL.md"
        if not skill_file.exists():
            print(f"  SKIP  {phase_slug} — no SKILL.md at {skill_file}")
            skipped += 1
            continue

        content = skill_file.read_text(encoding="utf-8")

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO skills (phase_slug, layer, content, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (phase_slug) DO UPDATE
                    SET content = EXCLUDED.content,
                        layer = EXCLUDED.layer,
                        updated_at = NOW()
                """,
                phase_slug, "phase-active", content,
            )

        print(f"  OK    {phase_slug} ({len(content):,} chars)")
        seeded += 1

    await pool.close()
    print(f"\nDone. {seeded} seeded, {skipped} skipped.")


if __name__ == "__main__":
    asyncio.run(seed())
