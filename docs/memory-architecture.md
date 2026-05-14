# Han Solo — Memory Architecture

**Status:** Design complete, pending build  
**Last updated:** 2026-05-14  
**Authors:** Scott, Ren, Claude Code

---

## Overview

Ren's memory is a four-tier system. Each tier has a defined lifespan, access pattern, and promotion path. Nothing is silently overwritten. Everything that moves between tiers is logged. Failures surface to Ren at session start.

---

## The Four Tiers

| Tier | Name | Store | Lifespan | Access |
|------|------|-------|----------|--------|
| T1 | Active Context | Letta core blocks | 3–5 days | Always in context |
| T2 | Recent Memory | Letta archival | 30–90 days | Searched on demand |
| T3 | Long-term Memory | Letta archival, tagged `tier:foundational` | Permanent | Searched on demand |
| T4 | Project Memory | Letta archival, tagged by project slug | Life of project | Searched by project |

---

## Tier 1 — Active Context

**Three core blocks, each with one job:**

| Block | Contents | Limit |
|-------|----------|-------|
| `session_current` | Current session only — who's here, session start time | 2,000 chars |
| `pending_thoughts` | Last 2–3 session briefs. Auto-trimmed by cron. | 8,000 chars |
| `open_threads` | Active flags, unresolved questions, things Ren must surface | 4,000 chars |

**What enters T1:**
- Synthesis cron writes a session brief to `pending_thoughts` after every conversation
- Ren writes directly at "This is the Way" close-out
- Claude Code writes a summary via MCP at session end
- Inline handoff summary written at every session reset

**Trim rule:** When synthesis cron runs and adds a new entry, it rewrites `pending_thoughts` to keep only the 2 most recent session briefs. Anything older gets promoted to T2 first, then removed.

---

## Tier 2 — Recent Memory

**What enters T2:**
- Promoted from T1 when a `pending_thoughts` entry is older than 3 days
- Written directly by synthesis cron as archival signals (bypasses T1)
- Written by Ren via `archival_memory_insert` during conversation
- Relationship signals, decisions, and project milestones enter here directly

**Lifespan:** 30–90 days. After 90 days, tagged `tier:foundational` and effectively becomes T3. No deletion — additive only.

---

## Tier 3 — Long-term Memory

**What enters T3:**
- Promoted from T2 at 90 days — entry gets tagged `tier:foundational`, stays in the same store
- Some things enter T3 directly: origin story, foundational decisions, things explicitly flagged as permanent
- MemPalace seeding enters here directly

**Deletion:** Never. T3 is permanent. Additive only.

**Tagging convention:** Every T3 entry carries `tier:foundational` in its text at write time so Ren's search can filter or weight by tier.

---

## Tier 4 — Project Memory

**One schema, two writers, no coordination overhead.**

### Record schema

```
project_id    — slug (deterministic, derived from project name)
entry_type    — decision | slice | status | context
source        — ren | claude_code
content       — the actual text
tier_tag      — t4 (always, for filtering)
```

### Writer responsibilities

| Writer | Owns | Entry types |
|--------|------|-------------|
| Ren | Strategy and design context | `decision`, `context` |
| Claude Code | Build execution | `slice`, `status` |

Neither writer overwrites the other's records. Both read everything.

### Project ID — slug convention

- Human name: "Handle — Customer Portal"
- Derived slug: `handle-customer-portal`
- Slug is the mechanical anchor. It never changes even if the project is renamed.
- When Ren hears "the Handle thing" she maps it to the slug. No clarification needed.

### Bootstrap flow

When a new project starts, Claude Code writes the first entry:
```
entry_type: context
source: claude_code
content: [project slug definition + initial scope]
```
This is the one exception to Ren owning `context` entries — the bootstrap record is written by Claude Code. After that, all `context` entries are Ren's domain.

### Project lifecycle

- Active: T4 entries written and refreshed as project evolves
- Closed: entries archived — tagged `project:closed`, stop being refreshed but remain searchable

---

## How Things Move Between Tiers

| Transition | Trigger | Executed by | Condition |
|-----------|---------|-------------|-----------|
| T1 → T2 | Entry older than 3 days | Synthesis cron | T2 write confirmed before T1 trim |
| T1 trim | After T1 → T2 promotion | Synthesis cron | Logged in `memory_transitions` |
| T2 → T3 | Entry approaching 90 days | Synthesis cron | Tag added, no deletion |
| T1 → T4 | Project milestone or decision | Ren or Claude Code | Written directly, bypasses T1 |

**Core invariant:** Nothing is removed from a lower tier until the write to the higher tier is confirmed.

---

## The Failsafe Layer

### memory_transitions table (PostgreSQL)

Every tier transition — whether it succeeds or fails — writes a record here first.

```sql
CREATE TABLE memory_transitions (
    id           SERIAL PRIMARY KEY,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    from_tier    TEXT NOT NULL,
    to_tier      TEXT NOT NULL,
    content_key  TEXT NOT NULL,
    status       TEXT NOT NULL,  -- 'pending' | 'success' | 'failed'
    completed_at TIMESTAMPTZ,
    error        TEXT
);
```

### Failure modes and handling

| Failure | What happens | Recovery |
|---------|-------------|---------|
| T2 write fails | Entry stays in T1, failure logged, retried next cron run | Ren flags at session start if > 1 failure |
| T1 trim fails after T2 write | Warning logged, T1 entry stays (harmless — slightly stale) | Cleaned up next cron run |
| Cron fails to run > 6 hours | Health flag set in `session_current` | Ren surfaces at session start |
| Synthesis API call fails | Raw transcript stays unprocessed in DB | Retried next cron run, never lost |

### Session start health check

Ren reads a summary of `memory_transitions` at every session start. She flags:
- Any `status: failed` entries from the last 24 hours
- Cron gap > 6 hours
- `pending_thoughts` within 500 chars of its 8,000 char limit

---

## What Ren Does vs. What the System Does

| Action | Ren | Synthesis Cron | Claude Code |
|--------|-----|----------------|-------------|
| Write session brief to T1 | ✓ (close-out) | ✓ (primary, backup) | ✓ (session end) |
| Promote T1 → T2 | — | ✓ | — |
| Trim T1 after promotion | — | ✓ | — |
| Write archival signals to T2 | ✓ (during conversation) | ✓ | — |
| Tag T3 entries | — | ✓ | — |
| Write T4 project context | ✓ (decision, context) | — | ✓ (slice, status) |
| Search T2 / T3 / T4 | ✓ | — | ✓ |
| Flag memory health issues | ✓ (session start) | — (logs only) | — |

---

## Open Questions (Pre-Build)

1. **T4 bootstrap timing** — does Claude Code write the bootstrap entry at project creation (start skill) or at first slice? Needs a decision before T4 build.

2. **`open_threads` ownership** — who trims it? Ren during close-out, or the cron? Probably Ren — she knows what's actually resolved.

3. **Primary interface question** — when does Scott use Ren vs. Claude Code for design work? This affects how and when T4 gets written. Still unresolved.

4. **project_id registry** — `projects.md` in engineering-playbook currently tracks active projects. T4 slugs need to align with that registry. Who keeps them in sync?
