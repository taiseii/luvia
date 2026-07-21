---
title: "Reference-manifest resolver (role to file, portrait fallback)"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`)

## What to build

A pure-function resolver that maps a persona-chosen `reference_role` to a concrete reference image file, reading a `manifest.json` colocated with the images on the box. The assets directory comes from the `LUVIA_SOPHIA_ASSETS` env var. Per-image schema: `{file, role (canonical_face|pose), framing (portrait|half|full), setting, tags[], description, default}`. The manifest is 5 static rows, not a DB table. When a role is missing or unspecified, the resolver falls back to the portrait (canonical face, the default). No code-side fuzzy scene matching — the role is picked upstream by the LLM; this slice only resolves role to file and applies the fallback.

## Acceptance criteria

- [ ] Reads assets dir from `LUVIA_SOPHIA_ASSETS`; parses `manifest.json` with the per-image schema above
- [ ] Resolves a valid role to its file; returns portrait (default) when role is missing/unspecified
- [ ] Pure function tests over a temp assets dir + `manifest.json` fixture — no network
- [ ] No auto-growth / no writing back to the manifest; resolution is read-only
- [ ] Named to disambiguate from the existing content manifest (this is the "reference manifest")

## Blocked by

None - can start immediately
