---
title: "luvia_selfie tool — integration + graceful soft-fail"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`)

## What to build

The `luvia_selfie(scene, reference_role)` tool in the `luvia_*` surface — the first offline-demoable end-to-end path. It composes the four seams: sanitize the scene (0013), resolve the reference (0014), check quota (0012), call the backend (0015), write a `selfie_log` row on success, and save the image to a box path which it returns. `scene` = free-text description of the shot; `reference_role` = which reference to edit from (`canonical_face` default, or a pose role). On any failure (sanitizer reject, quota cap, backend/delivery error) it returns a soft-fail result the persona can absorb in character — it never raises to the chat. A failed generation must NOT consume quota (no `selfie_log` row on failure). Delivery itself is not built here: the tool returns the path, and the persona delivers via the existing `send_message` tool using `MEDIA:<path> <caption>` (resolved shape A) — wired in the skill (0017).

## Acceptance criteria

- [ ] `luvia_selfie(scene, reference_role)` registered in the `luvia_*` tool surface; `canonical_face` is the default role
- [ ] Happy path: sanitize -> resolve -> quota-ok -> backend -> save to box path -> write `selfie_log` row -> return path
- [ ] Sanitizer reject, quota cap, and backend/delivery failure each return a soft-fail shape (never raises); no `selfie_log` row written on any failure (a failed generation does not consume quota)
- [ ] Tested via the tool seam against a temp SQLite db with backend and delivery injected/monkeypatched — no network
- [ ] Assertions cover quota enforcement, reference resolution, sanitizer application, `selfie_log` writes, and returned/soft-fail payload shapes — externally observable behavior only
- [ ] Prior art followed: `test_record_result.py`, `test_pacing.py`, `test_plan_today.py`

## Blocked by

- `docs/issues/0012-selfie-log-quota-helpers.md`
- `docs/issues/0013-prompt-sanitizer-content-ceiling.md`
- `docs/issues/0014-reference-manifest-resolver.md`
- `docs/issues/0015-bfl-flux2-backend.md`
