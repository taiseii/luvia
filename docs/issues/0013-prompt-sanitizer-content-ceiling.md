---
title: "Prompt sanitizer — hard no-nudity content ceiling"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`)

## What to build

A pure-function prompt sanitizer that enforces the non-negotiable content ceiling before any image is generated. Suggestive-but-clothed scenes pass through unchanged (lingerie/underwear, bedroom, flirty framing). Full nudity, exposed genitals/breasts, and explicit acts are rejected. This is a hard rule baked into code, not a persona or onboarding dial — no conversation or setting can raise the ceiling. It runs before any backend call; the second enforcement layer (BFL `safety_tolerance` at call time) lands with the backend in 0015. This is the security-critical seam and gets the most test cases.

## Acceptance criteria

- [ ] Pure function: scene text in, verdict out (pass / reject), no DB, no network
- [ ] Table-driven tests: suggestive-but-clothed prompts pass unchanged; nudity/explicit prompts rejected
- [ ] Ceiling is a hard rule with no parameter, env, or persona hook that can raise it
- [ ] Reject verdict is shaped so the caller can turn it into a soft in-character deflection (surfaced by the tool in 0016), never a raised error to the chat
- [ ] Edge/adversarial cases covered (euphemism, drift, mixed clothed+explicit phrasing)

## Blocked by

None - can start immediately
