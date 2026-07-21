---
title: "Role-aware first-person selfie POV in luvia_selfie"
status: ready-for-agent
labels: [ready-for-agent, hitl]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`).
Design records: `docs/adr/0002-bfl-direct-fixed-reference-library.md`,
`CONTEXT.md` (Selfie).

## What to build

Make generated selfies read as real first-person phone shots instead of third-person studio
portraits. The reference library is 3rd-person studio imagery, and the persona's `scene` goes
to the backend verbatim, so output looks like "someone photographed her" — the opposite of a
selfie (see the sharpened Selfie glossary entry).

Impose a first-person POV in code, in `luvia_selfie`, wrapping the persona-supplied scene
before the backend call — the persona keeps deciding *when* and *what scene*, never *how it's
shot* (same capability/persona split as ADR-0001, same reason `safety_tolerance` is pinned in
code). The POV is **role-aware**, keyed on `reference_role`:

- `canonical_face`, `half_body`, `work_look` → front-camera, arm's-length, slightly high angle,
  candid amateur phone snapshot.
- `full_body_seated`, `full_body_standing` → mirror selfie (phone visible in hand) — an
  arm's-length shot can't physically show a full body.

Accept that a mirror shot is a larger edit off a clean studio portrait, so identity fidelity
risk is slightly higher on full-body roles; the fallback is the persona picking a mid-role.

## Acceptance criteria

- [ ] `luvia_selfie` wraps the persona scene with a POV prefix selected by `reference_role`
- [ ] Front-camera framing for close/mid roles; mirror-selfie framing for the two full-body
      roles
- [ ] The backend stays a dumb, swappable transport — no POV logic leaks into it
- [ ] Live (HITL, real FLUX spend): a generated selfie reads as a first-person phone selfie,
      not a 3rd-person portrait, and the face is still recognizably the persona

## Blocked by

None — can start immediately, independent of 0019. (Shares `skills/sophia-nl/SKILL.md` with
0019; coordinate edits to avoid a merge conflict.)
