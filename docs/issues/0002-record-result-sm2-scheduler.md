---
title: "luvia_record_result + SM-2 behind the swappable scheduler interface"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0002 — Plugin Skeleton (`docs/prd/0002-plugin-skeleton.md`)

## What to build

The core practice loop: recording a result and rescheduling the item in one atomic tool
call, so no review event is ever logged without its scheduling effect (the carrier persona
must not be trusted to make two calls).

The scheduler lives behind a single interface with all algorithm parameters stored per item
as opaque state, never as schema columns — so SM-2 can later be swapped for FSRS with one
migration and zero data loss. Contract, decision-precise from the design session:

```python
def schedule(item_state: SchedulerState, grade: Grade, now: datetime) -> tuple[SchedulerState, datetime]
# Grade = again | good | easy | already_knew  (already_knew: first encounter only)
```

An SM-2 variant implements it first. `luvia_record_result` logs the full session event
(grade, timestamp, latency, comprehension-break flag) and updates the learner item's
scheduler state and due date in the same transaction. Latency is trusted from button-tap
flows and treated as noise from typed chat. Ambient exchanges record through the same tool
with implicit grades and the comprehension-break flag, so adaptation signals accumulate
without visible rubrics.

The `already_knew` branch is a follow-up slice (issue 0003); this slice ships the grade
enum in full but may reject `already_knew` with a clear error until 0003 lands.

## Acceptance criteria

- [ ] `luvia_record_result` writes the session event and the updated scheduler state/due date atomically — a forced failure mid-call leaves neither
- [ ] Scheduler tested table-driven through its public interface: grade sequences produce expected interval progressions for again/good/easy
- [ ] All SM-2 parameters live inside `scheduler_state_json`; no algorithm columns added to the schema
- [ ] A second scheduler implementation registered in tests proves swappability (state opacity)
- [ ] Session events store grade, timestamp, latency, and comprehension-break flag; every field asserted from resulting rows
- [ ] Recording an ambient exchange with a comprehension break is queryable afterwards

## Blocked by

- 0001-walking-skeleton-schema-setup
