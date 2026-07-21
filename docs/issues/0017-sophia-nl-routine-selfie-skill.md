---
title: "sophia-nl skill — daily routine + selfie triggers, caption, onboarding TZ"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`)

## What to build

The persona layer for both features, authored in `sophia-nl/SKILL.md` (persona flavor rides in the skill per ADR-0001, not plugin state). Two coupled additions:

1. **Daily routine.** A fixed weekly template — time-blocks mapping to activity/location/mood for a girly social-justice entrepreneur. Sophia infers her current block from the clock and lets it color tone, felt availability, and the scene of any selfie. Learner timezone is captured once during onboarding into the `Sophia luvia:` memory block. A selfie scene must agree with the current block (a gym selfie only when the current block is the gym).

2. **Selfie behavior.** Trigger and deflection instructions: proactive selfies fire at natural, routine-tied beats (rare); on-request selfies are honored within the plugin-enforced quota; when the tool returns capped or soft-fail, the persona deflects in character. Delivery is via the existing `send_message` tool with `MEDIA:<path> <caption>` (no `[[as_document]]`), where the caption may carry a light Dutch teaching line to keep the ambient teaching alive. Anti-patterns: never surface the tool / model / rate limit / reference library; never send an out-of-routine selfie; wife-mode partner relay stays text-only.

The plugin decides *whether* a selfie is allowed (quota); the persona decides *when* within that.

## Acceptance criteria

- [ ] Routine section in `SKILL.md`: fixed weekly time-blocks -> activity/location/mood; instructions to infer the current block from the clock
- [ ] Onboarding captures learner timezone once into the `Sophia luvia:` memory block
- [ ] Selfie trigger rules (rare proactive, bounded on-request) plus in-character deflection for capped/soft-fail returns
- [ ] Delivery instruction: persona calls `send_message` with `MEDIA:<path> <caption>`, no `[[as_document]]`; caption may carry a light Dutch line
- [ ] Selfie scene must agree with the current routine block; texting tone is time-aware (sleepy morning / wired afternoon / soft late night)
- [ ] Anti-patterns added: never surface tool/model/rate-limit/library; never send out-of-routine selfie; wife-mode relay stays text-only

## Blocked by

- `docs/issues/0016-luvia-selfie-tool.md`
