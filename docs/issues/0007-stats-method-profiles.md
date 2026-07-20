---
title: "luvia_stats + method profiles (luvia_set_method)"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0002 — Plugin Skeleton (`docs/prd/0002-plugin-skeleton.md`)

## What to build

Progress visibility and method selection, completing the Phase 1 tool surface.

`luvia_stats` answers "is this working": recall rate, sweep progress, pacing-band position,
and due counts, computed from SQLite state alone.

Method profiles load from YAML into the method profiles table; Phase 1 ships
`frequency_srs` and `communicative_hybrid` (informal register, adaptive language mix —
mixing logic itself is out of scope, only its input signals are logged).
`luvia_set_method` switches the learner's active profile.

## Acceptance criteria

- [ ] `luvia_stats` returns recall rate, sweep progress, band position, and due counts; values asserted against fixture histories
- [ ] Stats computed entirely from the SQLite file (cron-safe, no chat context)
- [ ] YAML profiles load into the method profiles table; `frequency_srs` and `communicative_hybrid` ship
- [ ] `luvia_set_method` switches the active profile and persists across a fresh call
- [ ] Both tools declared in the manifest; Phase 1 tool surface complete (setup, plan-today, pick-items, record-result, score-response, set-method, stats)

## Blocked by

- 0006-pacing-band-plan-today
