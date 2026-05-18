# T4 Design — Project Memory Layer

**Session:** 2026-05-18
**Status:** Design complete — ready to build

---

## What T4 Is

T4 is the project-specific tier of Han Solo's memory. Every artifact the Solo Builder Framework produces across a full build cycle lives here, tagged by project and type. Ren reads T4 at session start to orient on any active project — where it is, what's been decided, what's in flight.

All T4 passages in Letta are tagged: `[t4] [project:{slug}] [type:{entry_type}]`

---

## Three Tools

### `write_t4_entry`
Writes a T4 artifact to Letta. Write behavior is derived automatically from `entry_type` — the caller never specifies it.

**Parameters:**
```
project_slug: str          # "fantasy-football", "garden-planner", "solo-companion"
entry_type: str            # see entry type table below
entry_id: str | None       # required for hierarchy entries; auto-set for structural artifacts
parent_id: str | None      # required for deliverable (phase ID) and slice (deliverable ID)

# Typed fields — hierarchy entries (phase, deliverable, slice)
plain_language: str | None
technical_description: str | None
status: str | None
acceptance_criteria: list | None

# Slice-specific typed fields
anchor_design: str | None
anchor_data: str | None
anchor_done: str | None
anchor_process: str | None
done_criteria: list | None
quality_contract: str | None
dependencies: list | None

# Structural artifacts — free-form markdown
content: str | None
```

**Write behavior derived from entry_type:**
- `write_once` — rejects if entry already exists; call is a no-op with a warning
- `upsert` — creates if new, replaces if exists
- `append` — always adds new content to the existing entry

### `get_t4_entry`
Direct lookup by project + type + ID.

```
project_slug: str
entry_type: str
entry_id: str | None       # omit for auto-ID entries
```

Returns the full passage content or null if not found.

### `search_t4`
Semantic search scoped to a project.

```
project_slug: str
query: str
entry_type: str | None     # optional filter
limit: int                 # default 10
```

Uses existing Letta archival search filtered to `[t4] [project:{slug}]`.

---

## Entry Type Reference

| Entry type | Mode | entry_id | parent_id | Content mode |
|---|---|---|---|---|
| `phase` | Upsert | P1, P2… | — | Typed |
| `deliverable` | Upsert | D-01, D-02… | Phase ID | Typed |
| `slice` | Upsert | SL-001… | Deliverable ID | Typed |
| `discovery_brief` | Append | Auto | — | Free-form |
| `brainstorm` | Append | Auto | — | Free-form |
| `tech_context` | Write once | Auto | — | Free-form |
| `data_mapping` | Write once | Auto | — | Free-form |
| `design_identity` | Write once | Auto | — | Free-form |
| `as_is_map` | Append | Auto | — | Free-form |
| `to_be_map` | Append | Auto | — | Free-form |
| `sprint_screen` | Write once | screen slug | — | Structured summary + file path |
| `research_gaps` | Write once | Auto | — | Free-form |
| `deferred_decisions` | Upsert | Auto | — | Free-form |
| `handoff` | Upsert | Auto | — | Free-form |
| `decisions_log` | Append | Auto | — | Free-form |
| `current_phase` | Upsert | Auto | — | Free-form |
| `metrics` | Upsert | Auto | — | Free-form |
| `retro` | Write once per phase | Phase ID | — | Free-form |

---

## Sprint Screen Entry Format

Sprint screens store a structured summary, not the full HTML. Format:

```
Screen: {slug}
File: docs/design/{filename}.html
Phase: {phase where this screen is used}
Key elements: {comma-separated list of major UI elements}
Data points displayed: {comma-separated list of data fields visible on screen}
Interactive elements: {comma-separated list}
Design contract: mandatory — open full file at build, QA, and phase-test
```

---

## Hierarchy

Phases, deliverables, and slices are nested objects. Parent IDs link them:

```
Phase (P1)
  └── Deliverable (D-01, parent: P1)
        └── Slice (SL-001, parent: D-01)
```

`get_t4_entry` can traverse up: fetch a slice, follow `parent_id` to get its deliverable, follow again to get its phase.

---

## Rules

1. `discovery_brief` and `brainstorm` are one per project. Additional scope appends — never creates a new entry.
2. `as_is_map` and `to_be_map` are one per project. Additional flows append as named sections.
3. Hierarchy entries (`phase`, `deliverable`, `slice`) always require `plain_language` and `technical_description`. Reject if missing.
4. `slice` always requires `parent_id` (deliverable ID). `deliverable` always requires `parent_id` (phase ID).
5. Sprint HTML files are mandatory reads at build, QA, and phase-test — the T4 entry is an index, not a replacement.

---

## Framework Fixes Pending (Notecards 1–3)

These are curator-tracked, not part of the T4 build:

1. **Discovery brief + brainstorm** — skills must append to existing docs, never create new files for additional scope
2. **Process maps** — same rule; as-is and to-be are one per project
3. **Sprint screen gate** — QA and phase-test skills need explicit mandatory-open requirement for design files

Cleanup needed on existing projects (Solo Companion, Garden) to merge duplicate files before T4 ingest runs on those projects.
