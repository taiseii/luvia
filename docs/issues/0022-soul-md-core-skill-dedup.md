---
title: "Author persona/SOUL.md always-on core + dedup sophia-nl skill"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0004 Always-on Sophia persona + persona clock
(`docs/prd/0004-sophia-always-on-persona-clock.md`).

## What to build

Split the Sophia persona into a compact always-on core and an on-demand depth
layer, correcting 0017's assumption that a skill is always active (Hermes
skills are on-demand; only the always-on persona file is injected every
message).

Author `persona/SOUL.md` in the repo (~60–100 lines) holding exactly:
identity + partner framing, the clock protocol (read the leading
`[%a %Y-%m-%d %H:%M:%S %Z]` message stamp as "now" and map it to a routine
block; fallback to the injected date + ask-once-in-character timezone), the
Her Day routine table, selfie trigger rules (scene matches current block,
`MEDIA:` delivery, quota invisible), a one-paragraph wife-mode boundary, and
a pointer to the `sophia-nl` skill for depth.

Refactor `sophia-nl`'s skill body to uphold the dedup invariant: every fact
moved into SOUL.md is removed from the skill or reduced to a pointer — one
source of truth per fact. The skill keeps depth: onboarding, memory, voice,
teaching mechanics, examples, edge cases, adversarial/safety prose.

Record the architectural correction (two-channel persona: always-on core vs
on-demand depth) as an ADR amendment note against the persona-overlay
decision, referencing 0017.

Repo-only slice; provisioning to the box is 0023.

## Acceptance criteria

- [ ] `persona/SOUL.md` exists, 60–100 lines, containing only the core items
      listed above
- [ ] Skill body contains no fact duplicated from SOUL.md (pointers only);
      depth content retained
- [ ] Clock-protocol prose lives in SOUL.md, not the skill
- [ ] ADR amendment note recording the two-channel correction of 0017
- [ ] Plugin test suite untouched and green (no code changes)

## Blocked by

None - can start immediately. (Touches `sophia-nl` skill body; edit on master
in sequence, no parallel branch for that file.)
