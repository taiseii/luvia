---
title: "luvia_set_method + sessions honor active profile"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

Issue 0007 — luvia_stats + method profiles (`docs/issues/0007-stats-method-profiles.md`)

## What to build

`luvia_set_method(user_id, method_profile_id)` switches the learner's active method
profile, and session-open honors it instead of the hardcoded `'default'`.

The active profile is persisted per learner in `users.metadata_json` (no schema change —
matches the onboarding-context pattern already used by `luvia_setup`). Setting an
unknown profile id is rejected. The choice persists across a fresh tool call.

Session-open (`_resolve_session`) reads the learner's active method to stamp
`sessions.method_profile_id` rather than always writing `'default'`; learners with no
active method set fall back to a sensible default.

With this slice the Phase 1 tool surface is complete: setup, plan-today, pick-items,
record-result, score-response, set-method, stats.

## Acceptance criteria

- [ ] `luvia_set_method` switches the active profile and persists it in `users.metadata_json`
- [ ] Active profile persists across a fresh call (read back from SQLite)
- [ ] Setting an unknown `method_profile_id` is rejected
- [ ] New sessions stamp `method_profile_id` from the learner's active method, not hardcoded `'default'`
- [ ] Declared in the manifest; Phase 1 tool surface complete

## Blocked by

- Issue 0010 — Method profiles YAML loader (`docs/issues/0010-method-profiles-loader.md`)
