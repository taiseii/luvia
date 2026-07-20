---
title: "Method profiles YAML loader"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

Issue 0007 — luvia_stats + method profiles (`docs/issues/0007-stats-method-profiles.md`)

## What to build

Load method profiles from YAML into the `method_profiles` table so Phase 1 ships two
profiles: `frequency_srs` and `communicative_hybrid`.

`communicative_hybrid` is informal-register with an adaptive language mix — the mixing
logic itself is out of scope; the profile only declares the input signals that logic
would later read. Each profile stores its `config_yaml` alongside `label` and `version`.

Loading is idempotent: re-running against an existing DB upserts by `id` rather than
duplicating rows or bumping versions spuriously.

## Acceptance criteria

- [ ] YAML profiles load into the `method_profiles` table
- [ ] `frequency_srs` and `communicative_hybrid` both ship, each with its config
- [ ] `communicative_hybrid` declares its mix input signals only (no mixing logic)
- [ ] Loader is idempotent — a second run does not duplicate rows
- [ ] Tests assert both rows land with expected id / label / config

## Blocked by

- None - can start immediately
