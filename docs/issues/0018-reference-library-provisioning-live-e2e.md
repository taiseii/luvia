---
title: "Reference library provisioning + live end-to-end on box (HITL)"
status: ready-for-agent
labels: [ready-for-agent, hitl]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`)

## What to build

The live tracer bullet. Hand-curate the 5 fixed reference images (1 canonical portrait + 4 pose shots) into `assets/sophie/` ON THE BOX ONLY, author the colocated `manifest.json` (per-image role/framing/setting/tags/description/default), set env vars (`FLUX_API` = the `bfl_…` key, `LUVIA_SOPHIA_ASSETS` = the assets dir), and confirm a real selfie generates and delivers into the Telegram chat end-to-end. This slice is HITL: the reference set is hand-curated (human judgment on likeness), it touches a live box with real API spend, and it verifies real Telegram delivery. The library is fixed — never auto-grown from generated output (drift avoidance). Guard: `assets/sophie/` stays gitignored (already in place) and never lands in the public repo.

## Provisioning path

Reference images + `manifest.json` are NOT in git (`assets/sophie/` gitignored; repo is public). They reach the box out-of-band via direct file transfer (scp/rsync over the Tailscale SSH link) into the box's `LUVIA_SOPHIA_ASSETS` dir — never `git pull`. The 5 jpgs and the pre-authored `manifest.json` already exist locally under `assets/sophie/`; provisioning = transfer that directory verbatim, then set env + validate on-box.

## Acceptance criteria

- [ ] 5 curated reference images placed in `assets/sophie/` on the box (portrait + 4 poses); confirmed NOT tracked in git
- [ ] `manifest.json` transferred to the box (pre-authored locally at `assets/sophie/manifest.json` — a bare JSON array validated against the 0014 resolver: 5 rows, `potrait.jpg` as the `canonical_face` default row, 4 `pose` rows); on-box `load_reference_manifest()` loads it and resolves `canonical_face`/`pose`/unknown-role-fallback
- [ ] Placeholder human-readable fields refined before the live shot: the 4 pose rows' `framing`/`setting`/`description`/`tags` currently hold generic guesses (authored without seeing image content) — set them to match each actual shot, since the persona uses them to pick a role and seed the scene prompt
- [ ] `FLUX_API` and `LUVIA_SOPHIA_ASSETS` env vars set on the box
- [ ] One real proactive-or-request selfie generated via `luvia_selfie` and delivered into the Telegram chat via `send_message MEDIA:` — face recognizably Sophia
- [ ] `selfie_log` row written for the live generation; quota decremented as expected
- [ ] Confirmed the library is fixed (no path feeds generated output back as a new reference)

## Blocked by

- `docs/issues/0016-luvia-selfie-tool.md`
- `docs/issues/0017-sophia-nl-routine-selfie-skill.md`
