---
title: "BFL FLUX.2 pro backend behind generate-image interface"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`)

## What to build

A thin, swappable generate-image backend for Black Forest Labs FLUX.2 pro (direct API, per ADR-0002). One method: given a reference image (fed inline as base64) and a scene prompt, return image bytes. The API key is read from the `FLUX_API` env var (`bfl_…`); this is explicitly NOT the Hermes-native FAL `image_generate` tool. The reference goes in inline as base64 and the result is downloaded — nothing is uploaded to a public URL or third-party host. Sends BFL's server-side `safety_tolerance` as the second content-enforcement layer (the first is the sanitizer in 0013). The whole thing sits behind a one-method interface so moving off BFL (or adding FAL later) is a one-file change.

## Acceptance criteria

- [ ] One-method interface: `(reference_image, scene_prompt) -> image_bytes`, implemented for BFL FLUX.2 pro direct API
- [ ] Key read from `FLUX_API` env; reference sent inline as base64; result downloaded, never published to a URL
- [ ] `safety_tolerance` sent on every call as the second content ceiling
- [ ] Backend swappable behind the interface (BFL is one implementation; no BFL specifics leak past the seam)
- [ ] Tests exercise the interface with the HTTP call mocked/injected — no live network; assert request shape (base64 reference, safety_tolerance present) and bytes-out handling
- [ ] Backend errors surface as a clean failure the caller can turn into a soft-fail (consumed by the tool in 0016)

## Blocked by

None - can start immediately
