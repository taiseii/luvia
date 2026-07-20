---
title: "Walking skeleton: plugin package, manifest, schema, luvia_setup"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0002 — Plugin Skeleton (`docs/prd/0002-plugin-skeleton.md`)

## What to build

The first end-to-end path through the Luvia plugin: a Python plugin package with a YAML
manifest following Hermes conventions (snake_case `luvia_*` tool names), the full SQLite
schema from the spec, and the `luvia_setup` tool that onboards a learner — creating the
user row and capturing interests and contexts so content tagging and phrase seeding have
real data.

The full schema ships here, not just the tables this slice touches: users, languages,
content items, item tags, learner items (composite user+item key, generic columns plus
`scheduler_state_json`), sessions (mode: ambient/review/conversation, gap-closed), session
events (grade enum, latency, comprehension-break flag), method profiles, and the dormant
experiment tables. Learner state is keyed by user and item so a second learner never
requires a schema rewrite.

The database file lives in the Hermes home directory on the server; the plugin reconstructs
all state from SQLite on every call (no reliance on chat context, per cron constraint).

This slice lands the schema first, which unblocks PRD 0001 (seed pipeline) immediately.

## Acceptance criteria

- [ ] Plugin package loads as a Python package with a YAML manifest declaring `luvia_setup`; manifest validated statically in tests
- [ ] Applying the schema to a fresh SQLite file creates every table from the spec, including dormant experiment tables
- [ ] Calling `luvia_setup` against a temp database creates the learner with interests and contexts; returned payload and resulting rows asserted in tests
- [ ] Calling `luvia_setup` twice is safe (no duplicate learner, no schema clobber)
- [ ] All state reconstructed from the SQLite file at call time — no module-level state carried between calls

## Blocked by

None - can start immediately
