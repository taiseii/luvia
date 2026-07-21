---
title: "selfie_log table + quota helpers"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`)

## What to build

Add the `selfie_log` table to the Phase 1 SQLite schema and the store/quota helpers that read it. One row per generated selfie, keyed by learner, carrying a UTC timestamp and a trigger source (`proactive` | `request`). Provide a quota function that, given a learner and "now", answers whether another selfie is allowed under the two plugin-enforced limits: proactive ≤ 1 per rolling 72h, on-request ≤ 3 per day. Quota is computed purely from logged history over trailing windows — same style as pacing's trailing-window reads. This slice ships the schema, the write helper, and the read/quota helper; the tool that calls them lands in 0016.

## Acceptance criteria

- [ ] `selfie_log` table added to `plugin/schema.sql` (learner key, UTC timestamp, `trigger_source` proactive|request)
- [ ] Store helper writes a selfie_log row; store/quota helper computes remaining allowance per source
- [ ] Proactive limit (1 per rolling 72h) and request limit (3 per day) asserted at their window edges via fixture histories across time (mirrors `test_pacing` / `test_plan_today` window-driven style)
- [ ] Quota computed entirely from the SQLite file, no chat context
- [ ] Tests assert externally observable behavior (rows written, quota verdicts), not internal call order

## Blocked by

None - can start immediately
