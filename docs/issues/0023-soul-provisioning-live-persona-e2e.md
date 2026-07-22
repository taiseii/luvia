---
title: "Provision SOUL.md to box + live persona e2e (completes 0018 gate)"
status: ready-for-agent
labels: [ready-for-agent, hitl]
---

## Parent

PRD 0004 Always-on Sophia persona + persona clock
(`docs/prd/0004-sophia-always-on-persona-clock.md`).

## What to build

Ship the always-on persona core to the box and prove the whole persona +
clock + selfie path live, completing the e2e that 0018 left blocked.

Provision the repo-authored `persona/SOUL.md` to the box's `HERMES_HOME`
persona file (same out-of-band scp pattern as the reference assets), restart
the gateway, then run the live HITL acceptance in a real Telegram session.
Before provisioning, re-confirm the box persona file is still empty and the
always-on injection path behaves as diagnosed.

Archive evidence PNGs like prior HITL runs (0020/0021 pattern).

## Acceptance criteria

- [ ] Box persona file contains the repo `persona/SOUL.md` content; gateway
      restarted cleanly
- [ ] Live: Sophia states the correct day and time-of-day (no "morning"
      greeting at night, no wrong weekday)
- [ ] Live: answers grounded in the current routine block ("what are you
      doing?" gets a block-appropriate answer, not "just here for you")
- [ ] Live: block-appropriate selfie delivered end-to-end via `luvia_selfie`
      into the chat — the 0018 e2e gate now passes
- [ ] Fallback: ask-once timezone prose reads in character if the stamp is
      absent
- [ ] Evidence PNGs archived (local gitignored dir + box archive)

## Blocked by

- 0022 (SOUL.md authored + skill dedup)
- 0019 (gateway message timestamps live on box)
