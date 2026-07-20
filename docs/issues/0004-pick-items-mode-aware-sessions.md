---
title: "luvia_pick_items mode-aware batches + gap-based sessions"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0002 — Plugin Skeleton (`docs/prd/0002-plugin-skeleton.md`)

## What to build

The content picker the carrier persona calls: `luvia_pick_items` returns a small ambient
micro-batch for weaving practice into conversation, or a due-review batch for the
button-graded review-mode flow, depending on the requested mode.

Activity is grouped into sessions as gap-based bursts with a mode column
(ambient/review/conversation) — no user-facing session ceremony. Picking and recording
attach to the current burst, closing it when the gap threshold passes, so ambient, review,
and conversation activity are analyzable separately.

New-item intake in this slice uses a fixed default allotment; the real pacing band wires in
via issue 0006.

## Acceptance criteria

- [ ] Review mode returns due items (due date ≤ now), capped at the requested batch size
- [ ] Ambient mode returns a small micro-batch mixing due items and new intake per the fixed default
- [ ] New items are drawn from content items the learner has no state for; sweeps and duplicates never re-offered within a batch
- [ ] Activity within the gap threshold lands in one session row with the correct mode; activity after the gap opens a new session
- [ ] Payloads and resulting session rows asserted against a temp database seeded with fixtures

## Blocked by

- 0002-record-result-sm2-scheduler
