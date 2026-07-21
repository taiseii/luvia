---
title: "Persona clock — enable gateway message timestamps + timezone + skill reads the stamp"
status: ready-for-agent
labels: [ready-for-agent, hitl]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`).
Design record: `docs/adr/0004-plugin-provided-persona-clock.md`.

## What to build

Give the carrier persona a reliable current time-of-day so its routine, tone, and selfie
scenes match the learner's local clock. Today Hermes injects only the date (UTC) into the
system prompt and never a time-of-day, so the persona guesses the routine block and greets
"goedemorgen" at 01:00.

Per ADR-0004 the fix is the host's own passive per-message clock, not a plugin tool. Hermes'
gateway has a `message_timestamps` feature (default OFF) that prefixes every inbound user
message with a timezone-aware `[%a %Y-%m-%d %H:%M:%S %Z]` stamp the model sees. Enable it and
set the timezone to the learner's, then teach the skill to read the stamp.

No plugin code — this is box config plus skill prose:

- Box `config.yaml`: `gateway.message_timestamps.enabled: true` and `timezone: Europe/Amsterdam`
  (also settable via `HERMES_TIMEZONE`). This makes the stamp render in the learner's zone and
  the host's injected date roll at the learner's midnight.
- sophia-nl skill: read the leading `[...]` stamp on the latest message as "now," map it to the
  routine block, and anchor texting tone/energy, felt availability, and any selfie scene to that
  block. Timezone is captured at onboarding into `users.timezone`; keep the ask-once-in-character
  fallback if it is ever missing.

Provision the box config through the durable Ansible wiring, bundled with the pending
`FLUX_API` + `LUVIA_SOPHIA_ASSETS` durable-wiring task — not a hand-edit that the next Ansible
run clobbers.

## Acceptance criteria

- [ ] `gateway.message_timestamps.enabled: true` and `timezone: Europe/Amsterdam` set on the box
      via durable Ansible wiring; the inbound-message stamp renders in CET/CEST, not UTC
- [ ] sophia-nl skill reads the leading `[...]` stamp as the current time and anchors tone /
      availability / selfie scene to the derived routine block; ask-once timezone fallback intact
- [ ] Live (HITL): the persona reports the correct time-of-day — no "morning" greeting at 01:00
      local — and its tone matches the current block
- [ ] No plugin/tool code added for the clock (host feature only, per ADR-0004)

## Blocked by

None — can start immediately. (Shares `skills/sophia-nl/SKILL.md` with 0020; coordinate edits
to avoid a merge conflict.)
