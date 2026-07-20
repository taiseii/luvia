---
title: "luvia_stats read tool"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

Issue 0007 — luvia_stats + method profiles (`docs/issues/0007-stats-method-profiles.md`)

## What to build

A read-only `luvia_stats(user_id, lang)` tool answering "is this working", computed
entirely from the SQLite file so it is cron-safe and needs no chat context.

It returns four signals:

- **recall rate** — genuine (non-sweep) grade success over a trailing window, reusing
  the same recall definition the pacing band folds over (`already_knew` sweeps excluded).
- **sweep progress** — how far the first-encounter fast-track sweep has advanced
  (swept vs. remaining).
- **band position** — current pacing band via `pacing.current_band` over the weekly
  history, plus the daily new-intake allotment it implies.
- **due counts** — how many `learner_items` are due now, broken out enough to be actionable.

## Acceptance criteria

- [ ] `luvia_stats` returns recall rate, sweep progress, band position, and due counts
- [ ] Values asserted against fixture histories (fresh learner, mid-sweep, ratcheted band)
- [ ] Computed entirely from the SQLite file — no chat context, cron-safe
- [ ] Sweep `already_knew` grades excluded from the recall figure, consistent with pacing
- [ ] Declared in the plugin manifest

## Blocked by

- None - can start immediately (0006 pacing band is merged)
