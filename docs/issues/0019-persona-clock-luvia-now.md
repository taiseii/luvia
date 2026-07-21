---
title: "Persona clock — luvia_now tool + local_time stamp + skill wake-sequence"
status: ready-for-agent
labels: [ready-for-agent, hitl]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`).
Design record: `docs/adr/0004-plugin-provided-persona-clock.md`.

## What to build

Give the carrier persona a reliable time-of-day so its routine, tone, and selfie scenes line
up with the learner's actual local clock. Today Hermes injects only the date (UTC) and never a
time-of-day, so the persona guesses the routine block and greets "goedemorgen" at 01:00.

Per ADR-0004 the clock is plugin-provided: a new `luvia_now` tool returns the learner's current
local time and weekday, computed from the stored `users.timezone`. The **skill** maps that raw
time to a routine block (the plugin never holds the block table — persona flavor stays in the
skill). Every other luvia tool result is additionally stamped with `local_time` as a backstop,
so any tool call refreshes the persona's clock even if it skips `luvia_now`.

The sophia-nl skill's wake-sequence becomes: recall memory → `luvia_now` → derive block →
(first exchange of the day only) `luvia_plan_today` → compose the reply anchored to the block.
The block anchors three things: texting tone/energy, felt availability, and any selfie scene.
If `users.timezone` is missing or invalid, the persona asks once in character and stores it.

Also set `HERMES_TIMEZONE=Europe/Amsterdam` on the box so the host's injected date rolls at the
learner's midnight (date-boundary correctness for `plan_today`'s once-per-day and
`last_plan_date`); do it through the durable Ansible wiring, not a hand-edited `.env`.

## Acceptance criteria

- [ ] `luvia_now` returns the learner's current local time + weekday computed from
      `users.timezone`; a missing/invalid timezone degrades safely (no crash, soft signal the
      skill can act on)
- [ ] Every luvia tool result carries a `local_time` field (backstop clock)
- [ ] sophia-nl skill calls `luvia_now` on each wake and anchors tone / availability / selfie
      scene to the derived routine block; timezone-ask-once fallback is wired
- [ ] Live (HITL): the persona reports the correct time-of-day — no "morning" greeting at 01:00
      local — and its tone matches the current block
- [ ] `HERMES_TIMEZONE=Europe/Amsterdam` set via durable Ansible wiring (bundled with the
      pending `FLUX_API` + `LUVIA_SOPHIA_ASSETS` durable-wiring task)

## Blocked by

None — can start immediately. (Shares `skills/sophia-nl/SKILL.md` with 0020; coordinate edits
to avoid a merge conflict.)
