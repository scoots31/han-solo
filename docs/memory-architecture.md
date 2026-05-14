# Han Solo — Memory Architecture

**Status:** Design locked — ready to build  
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

## Decisions Locked

1. **T4 bootstrap timing** — T4 is created at project creation, not first slice. Every framework phase that produces an artifact (brainstorm, discover, PRD, design) writes to T4 from day one. T4 is the full project record, not just the build record.

2. **`open_threads` ownership** — Ren owns trimming. She knows what's actually resolved vs. quieted down. The cron does not touch `open_threads`.

3. **Primary interface — pre and post bridge:**
   - *Pre-bridge (today):* Brainstorm and discovery can happen with Ren or in Claude Code — wherever the thinking flows. If produced with Ren, output is pasted into Claude Code to kick off the framework phase. Everything from design sprint through deploy runs in Claude Code, writing back to Ren's memory via MCP at session end.
   - *Post-bridge:* Same split, no manual seam. Artifacts produced with Ren write directly to T4. Claude Code reads them at session start. Both reading from the same source of truth throughout.
   - *T4 write source:* `source: ren` if artifact produced in Ren chat, `source: claude_code` if produced in the framework. Same schema either way.

4. **project_id registry** — declared in `projects.md` at project kickoff. T4 slug is derived from the project name at that moment and recorded there. One entry point, mechanical anchor never changes even if the project is renamed later.

---

## Build Plan

Builds are sequenced. Do not start a phase until the previous one is complete and verified.

---

### Phase 1 — T1 Foundation (build this first)

**Goal:** Three scoped core blocks, each with one job. `open_threads` doesn't exist yet.

**Steps:**
1. Create `open_threads` core block on ren-v2 via Letta API — empty, limit 4,000 chars
2. Add `memory_transitions` table to `db.py` — schema is in the Failsafe Layer section above. Table is created automatically on pool init.
3. Update `always_loaded_core` to reference `open_threads` as the place for active flags and unresolved questions
4. Verify all three T1 blocks are visible in the memory panel

**Files touched:** `han_solo/db.py`, Letta API (direct call to create block)

---

### Phase 2 — T1 → T2 Promotion (synthesis cron update)

**Goal:** Synthesis cron promotes old `pending_thoughts` entries to archival and trims the block. Every transition is logged.

**Steps:**
1. Add `log_transition()` function to `db.py` — writes to `memory_transitions` with status `pending`
2. Add `complete_transition()` — updates status to `success` or `failed` with timestamp and error
3. Update `scripts/synthesize.py` to add a second pass after transcript synthesis:
   - Parse `pending_thoughts` entries by `---` separator
   - Identify entries older than 3 days (by embedded date)
   - For each old entry: log transition intent → write to archival → confirm write → mark `success` → trim from `pending_thoughts`
   - If archival write fails: mark `failed`, leave entry in T1, move on
   - Rewrite `pending_thoughts` with only the 2 most recent entries after promotion pass completes
4. Add failed transition count to the health summary returned by `health_status()`

**Files touched:** `han_solo/db.py`, `scripts/synthesize.py`

**Invariant:** Nothing removed from T1 until T2 write is confirmed.

---

### Phase 3 — T2 → T3 Tagging (synthesis cron update)

**Goal:** Entries approaching 90 days in archival get tagged `tier:foundational`. No deletion.

**Steps:**
1. Update `scripts/synthesize.py` to add a third pass:
   - Query archival passages without `tier:foundational` tag
   - For each passage older than 90 days: append `[tier:foundational]` marker to text, rewrite passage
   - Log transition in `memory_transitions`
2. Verify Letta archival supports updating existing passages (PATCH on passage ID)

**Files touched:** `scripts/synthesize.py`

**Note:** If Letta v0.16.7 does not support passage updates, tag at write time instead — every new archival write includes an `inserted_at` date in the text so age can be calculated later.

---

### Phase 4 — T4 Project Memory

**Goal:** Project-scoped archival entries, written by both Ren and Claude Code using a shared schema.

**Steps:**
1. Add `write_t4_entry()` MCP tool — accepts `project_id`, `entry_type`, `source`, `content`. Formats and writes to archival with `[t4]` and `[project:{slug}]` tags.
2. Add `search_t4()` MCP tool — searches archival filtered by project slug tag
3. Update the framework `start` skill to write a bootstrap T4 entry at project creation (entry_type: context, source: claude_code)
4. Update `projects.md` template to include T4 slug field
5. Document Ren's write pattern: during design sessions she calls `write_t4_entry` for decisions and context

**Files touched:** `han_solo/server.py`, `han_solo/letta_client.py`, engineering-playbook `start` skill, `projects.md`

---

### Phase 5 — Health surfacing to Ren

**Goal:** Ren sees memory health at every session start without having to ask.

**Steps:**
1. Add `get_transition_failures()` to `db.py` — returns failed transitions from last 24 hours
2. Add transition failure count and last cron run time to `health_status()` response
3. Update `always_loaded_core` session health check instructions to include: check `memory_transitions` for recent failures via MCP, flag if any `status: failed` in last 24 hours
4. Add `/api/memory-health` endpoint that returns transition log summary — callable by Ren via MCP tool

**Files touched:** `han_solo/db.py`, `han_solo/server.py`, `always_loaded_core` block

---

### Build order summary

| Phase | What | Scope |
|-------|------|-------|
| 1 | T1 foundation — `open_threads` block + `memory_transitions` table | Small, start here |
| 2 | T1→T2 promotion in synthesis cron | Medium |
| 3 | T2→T3 tagging in synthesis cron | Small, depends on Phase 2 |
| 4 | T4 project memory — MCP tools + framework integration | Large, separate session |
| 5 | Health surfacing to Ren | Small, can run parallel with Phase 3 |
