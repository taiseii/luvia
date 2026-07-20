---
title: "Fast-track sweep: already_knew on first encounter"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0002 — Plugin Skeleton (`docs/prd/0002-plugin-skeleton.md`)

## What to build

The sweep path for a learner starting at A2: an "Already knew" grade, valid only on an
item's first encounter, that fast-tracks the item straight to a ~30-day interval with an
ease bump, skipping the graduation ladder. Existing vocabulary sweeps through without
tedium.

Fast-tracked items do not consume the pacing band — they are not genuinely new intake.
The band itself lands in issue 0006; this slice must record enough on the learner item or
event for 0006 to exclude sweeps from band accounting.

## Acceptance criteria

- [ ] `already_knew` through `luvia_record_result` on first encounter jumps the item to a ~30-day interval with an ease bump; interval asserted table-driven
- [ ] `already_knew` on any later encounter is rejected with a clear error
- [ ] Swept items are distinguishable from genuinely-new intake in stored state, so pacing-band accounting can exclude them
- [ ] Fast-track recording is atomic like any other grade

## Blocked by

- 0002-record-result-sm2-scheduler
