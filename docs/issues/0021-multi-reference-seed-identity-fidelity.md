---
title: "Multi-reference + pinned seed for selfie identity fidelity"
status: done
labels: [done, hitl]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`).
Design records: `docs/adr/0002-bfl-direct-fixed-reference-library.md`, `CONTEXT.md` (Selfie).
Follows 0020 (role-aware POV). Live HITL on 0020 confirmed identity holds on same-outfit
edits but drifts on aggressive outfit+setting swaps (gym, pajamas) — `docs/hitl/0020/`.

## Problem

Every generation feeds the backend a single reference image (`input_image`). The bigger the
edit off that one studio base — new outfit, new setting, new pose — the more of the frame the
model regenerates, the less it stays anchored to the reference face, so identity drifts. A
single anchor also means no shot-to-shot reproducibility: consecutive selfies can wander.

## What to build

Raise identity fidelity via two backend levers. Both live in the image backend only — the
POV/persona/quota seams above it are untouched, and the backend stays a dumb, swappable
transport (ADR-0002 / 0020 acceptance).

1. **Multi-reference input.** FLUX.2 pro accepts up to 8 input images
   (`input_image_2..input_image_8`, verified against BFL API docs). Send the resolved role
   image as the primary base *plus* a small fixed set of identity-anchor shots (at minimum
   `canonical_face`; ideally 2–3 face angles) as secondary references, so the model
   triangulates the face instead of extrapolating from one frame. The anchor set is fixed in
   code / manifest — the persona never chooses it (same capability/persona split as 0020).

2. **Pinned seed.** Thread a `seed` into the submit payload for reproducibility. Decide the
   policy: a stable per-persona seed (consistent face across all her selfies) vs. per-call
   deterministic. Default to a stable persona seed; make it overridable.

Reference-manifest change: define the identity-anchor set (which files are always sent as
secondary refs). Keep the role→primary-file resolution from 0014 intact; layer the anchors on
top so an unknown/missing role still falls back to `canonical_face` as today.

Out of scope: upgrading to `flux-2-max` (cost decision, separate) and curating new base
images for gym/bed (library-expansion, 0018 territory).

## Acceptance criteria

- [x] Submit payload carries the resolved role image as primary plus the fixed identity-anchor
      set as `input_image_2..N`
- [x] Anchor set is fixed in code/manifest; persona/scene cannot alter it
- [x] A `seed` is sent; policy documented (default stable per-persona, overridable) —
      `DEFAULT_SELFIE_SEED`, env `LUVIA_SELFIE_SEED` overrides, sentinel `0` opts out to random
- [x] Backend stays swappable transport — no persona/POV/quota logic leaks in; multi-ref +
      seed are backend-internal
- [x] Existing single-`input_image` behavior degrades gracefully if the anchor set is absent
- [x] Live (HITL, real FLUX spend): re-run the 0020 drift scenes (gym mid-workout, bed
      pajamas) and confirm the face holds measurably better than the single-ref baseline in
      `docs/hitl/0020/` — verified 2026-07-22: multi-ref + seed gens (`docs/hitl/0021/`) judged
      acceptable against the single-ref baseline on both drift scenes.

## Blocked by

None. Independent of 0018 (library expansion) and 0019 (persona clock). Touches
`plugin/image_backend.py` and `plugin/reference_manifest.py` — coordinate with any concurrent
0014/manifest edits.
