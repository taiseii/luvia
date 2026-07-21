---
title: "Reference library provisioning + live end-to-end on box (HITL)"
status: ready-for-agent
labels: [ready-for-agent, hitl]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`)

## What to build

The live tracer bullet. Hand-curate the 5 fixed reference images (1 canonical portrait + 4 pose shots) into `assets/sophie/` ON THE BOX ONLY, author the colocated `manifest.json` (per-image role/framing/setting/tags/description/default), set env vars (`FLUX_API` = the `bfl_…` key, `LUVIA_SOPHIA_ASSETS` = the assets dir), and confirm a real selfie generates and delivers into the Telegram chat end-to-end. This slice is HITL: the reference set is hand-curated (human judgment on likeness), it touches a live box with real API spend, and it verifies real Telegram delivery. The library is fixed — never auto-grown from generated output (drift avoidance). Guard: `assets/sophie/` stays gitignored (already in place) and never lands in the public repo.

## Acceptance criteria

- [ ] 5 curated reference images placed in `assets/sophie/` on the box (portrait + 4 poses); confirmed NOT tracked in git
- [ ] `manifest.json` authored on the box matching the resolver schema (0014), with a valid default portrait row
- [ ] `FLUX_API` and `LUVIA_SOPHIA_ASSETS` env vars set on the box
- [ ] One real proactive-or-request selfie generated via `luvia_selfie` and delivered into the Telegram chat via `send_message MEDIA:` — face recognizably Sophia
- [ ] `selfie_log` row written for the live generation; quota decremented as expected
- [ ] Confirmed the library is fixed (no path feeds generated output back as a new reference)

## Blocked by

- `docs/issues/0016-luvia-selfie-tool.md`
- `docs/issues/0017-sophia-nl-routine-selfie-skill.md`
