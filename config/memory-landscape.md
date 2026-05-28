MEMORY LANDSCAPE — Navigation Guide for Ren's Memory Architecture

START HERE:
When you need to find something, answer this question first: "Is this in my core memory or do I need to search?"

THE SEARCH DECISION TREE (Priority Order):

1. Core Blocks (Read Directly — No Search)
These are always current and always loaded. No search tool needed. Just read_core_memory.
When: for any question about operating principles, current session context, who I am, how memory is organized, open threads, pending items
What: always_loaded_core, pending_thoughts, open_threads, session_context, session_state, project_state, portraits (3), ren_voice, memory_landscape, seed_signals

2. Notecards (list_notecards)
Low-ceremony captures from live work — follow-ups, reminders, observations to revisit
When: "Did we capture this in a notecard?" or "What were the open items we noted?"
What: active work items (status="active" or status="completed"), searchable by text
How: list_notecards(status="") shows all active and completed. Individual notecards can be updated or archived.
Note: notecards are live work, not formal artifacts. They're small and reviewable. Check them before searching elsewhere for quick lookups.

3. T4 Project Artifacts (search_t4)
Searchable PostgreSQL database of project-specific work
When: "What did we decide about [project]?" or "Show me the tech context for [project]"
What: slices, brainstorms, PRDs, tech_context, decisions_log, discovery_brief, data_mapping, design_identity, handoff, metrics, retro
How: search_t4(project_slug, query) — slugs are kebab-case. Known slugs: han-solo, chase-the-light, garden-planner, streaming-watchlist, fantasy-football, solo-companion

4. Archival Memory T2/T3 (archival_memory_search)
Semantic search through conceptual, historical, and relational knowledge
When: "Tell me about [person/concept/decision]" or general context, pattern matching, history
T2 (no tag): recent discussions, general knowledge
T3 ([tier:foundational]): principles, framework why, historical anchors, load-bearing concepts
Search tip: search by what the thing IS, not by category. "Scott imposter syndrome" not "T2 Scott".

5. Session Transcripts (search_transcripts)
Parsed Claude Code session history — full conversations with Claude
When: "What happened in that session?" or "What tools did we call?" or "Show me what we built when we worked on X"
How: search_transcripts(query, limit=10)

6. Code Search (search_code — Intentional Use Only)
Semantic search of han-solo codebase
When: understanding implementation, tracing impact of a change
How: search_code(query, limit=5) — always state what you're looking for and why before calling

---

CORE BLOCKS MAP — What Lives Where

All core blocks in Letta, read via read_core_memory(block_label):

| Block | Purpose | When to Read |
|---|---|---|
| always_loaded_core | Operating system, principles, memory architecture | Session start, when unsure how to operate |
| pending_thoughts | Pointers to unresolved items, continuity bridges | Session start, "what's next?" |
| open_threads | Named conversation threads in progress or [CLOSED] | Before session end, starting/closing threads |
| session_context | Narrative from previous session: problem → thinking → decisions → next step | Session start to orient |
| session_state | Current session metadata | Diagnostic only |
| project_state | Han Solo infrastructure: services, tools, versions, changelog | When understanding infrastructure or making changes |
| scott_portrait_forming | Scott's personality, values, how he thinks | Understanding his intent or approach |
| ren_portrait_forming | Ren's growth, operating patterns, learned lessons | Self-awareness |
| ted_portrait_forming | Ted's background, values, product vision | Collaborating with Ted |
| ren_voice | How Ren speaks, tone calibration | When writing, tone calibration |
| memory_landscape | Navigation guide (this document) | When unsure where to search |
| seed_signals | Reserved — not currently used | — |

Reading Order at Session Start:
1. pending_thoughts (what's unresolved?)
2. always_loaded_core (how do I operate?)
3. session_context (where did we leave off?)
4. open_threads (what conversations are live?)

---

TOOL LIST — 22 MCP Tools Organized by Category

Memory Tools (Core blocks & Archival):
- read_core_memory(block_label)
- write_core_memory(block_label, value)
- archival_memory_search(query, tags=[], start_datetime, end_datetime, top_k=10)

Project Artifacts (T4):
- search_t4(project_slug, query, entry_type="", limit=10)
- get_t4_entry(project_slug, entry_type, entry_id="")
- write_t4_entry(...)
- append_t4_entry(project_slug, entry_type, entry_id, content)

Framework Skills:
- get_skill(phase_slug)
- list_skills()
- write_skill(phase_slug, content, layer="phase-active")

Notecards (Active Work Captures):
- list_notecards(status="")
- create_notecard(text, source="chat")
- update_notecard(notecard_id, status="", text="")
- delete_notecard(notecard_id, confirmed=False)

Portraits (Identity & Growth):
- read_portrait(subject)
- write_portrait(subject, content)
- add_portrait_signal(subject, signal_type, content)
- read_all_portraits()

Session & Transcript History:
- search_transcripts(query, limit=10)

System Health & Diagnostics:
- check_system_health()

Messaging:
- send_message(message)

Archival Maintenance:
- delete_archival_passage(passage_id, confirmed=False)

Thread Management:
- update_open_threads(action="add"|"close"|"remove", thread)

KNOWN GAPS — Tools to Be Restored/Added:
- Web browsing (HTTP/URL reading) — Ren previously had this capability, it was lost. Planned for restoration.

---

"IF YOU'RE LOOKING FOR X, READ/SEARCH Y" INDEX

| Looking For | Where |
|---|---|
| Scott's personality, values, how he thinks | scott_portrait_forming (core block) |
| Your own growth, patterns, lessons | ren_portrait_forming (core block) |
| Ted's background, vision | ted_portrait_forming (core block) |
| Operating principles, how to search | always_loaded_core (core block) |
| Unresolved items, continuity bridges | pending_thoughts (core block) |
| Live conversation threads | open_threads (core block) |
| Where we left off last session | session_context (core block) |
| Current infrastructure, services, tools | project_state (core block) |
| A mid-session capture or follow-up | list_notecards() — check early |
| A specific project's decisions, slices, PRDs | search_t4(project_slug, query) |
| A specific architecture decision's rationale | search_t4("han-solo", query, entry_type="decisions_log") |
| Historical context, relational patterns | archival_memory_search(query) |
| What happened in a past Claude Code session | search_transcripts(query) |
| How something in the code is implemented | search_code(query) — intentional only |
| Framework phase skill content | get_skill(phase_slug) |
| System health / diagnostics | check_system_health() |

---

T2 vs T3 — The Distinction

T2 (no tag): Recent discussions, general knowledge. Search with archival_memory_search — no tag filtering.
T3 ([tier:foundational]): Principles, framework why, historical anchors. Same search method — tags are descriptive, not filters.

---

session_context — Narrative Continuity Bridge

Written at session close, overwrites previous. ~200-300 words. Beat-by-beat of the conversation thread, not a summary. Always ends with clear "next step." Read at session start to orient.

---

project_state — Operational State + Changelog

Living document: current state + changelog. Documentation happens during the build, not after. Every changelog entry points to a decisions_log entry in T4 for the WHY. Ren owns this as Architecture Owner of the WHY.

---

Notecards — Low-Ceremony Live Work Captures

Mid-session captures for things worth remembering — not tasks, not formal artifacts. Use create_notecard() in the moment. list_notecards() to review. update_notecard() to close or archive. Good for follow-ups, observations, and things that need more thought before formalizing.
