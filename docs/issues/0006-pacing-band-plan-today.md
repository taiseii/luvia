---
title: "Pacing band + luvia_plan_today"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0002 — Plugin Skeleton (`docs/prd/0002-plugin-skeleton.md`)

## What to build

The pacing band and the daily plan built on it. The band governs genuinely-new intake:
35–70 items/week, starting at 50, ratcheted weekly on a trailing two-week window — recall
≥85% and daily completion move it up 5–10; recall <70% or 3+ skipped days move it down.
The binding constraint is the review-load ceiling (~100 touches/day): daily review load is
capped with overflow spilling forward, so one missed day never creates a guilt backlog.
New intake is never starved to zero. Completion is measured as the share of due items
cleared by end of day, not per-session. Sweeps (fast-tracked items from issue 0003) never
consume the band.

`luvia_plan_today` gives the carrier persona the day's plan: due load, new intake, and a
suggested mode balance, so it can pace the day's touches sensibly. This slice also replaces
the fixed new-intake default in `luvia_pick_items` (issue 0004) with the real band, so the
learner gets a guaranteed daily allotment of genuinely new items regardless of review
backlog.

Pacing logic is a pure function over review histories, per the PRD's testing decisions.

## Acceptance criteria

- [ ] Pacing tested as a pure function over synthetic review histories: ratchet up, ratchet down, floor (35), ceiling-binding, overflow spill
- [ ] Strong trailing recall and completion ratchet the band up 5–10; weak recall or 3+ skipped days ratchet it down; band stays within 35–70
- [ ] Review-load ceiling caps the day; overflow spills forward; new intake never reaches zero
- [ ] Fast-tracked sweeps excluded from band consumption
- [ ] `luvia_plan_today` returns due load, new intake, and suggested mode balance from SQLite state alone (cron-safe, no chat context)
- [ ] `luvia_pick_items` new intake now governed by the band; daily new-item allotment guaranteed even with a review backlog

## Blocked by

- 0003-fast-track-sweep
- 0004-pick-items-mode-aware-sessions
