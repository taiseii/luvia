---
title: Always-on Sophia persona (SOUL.md) + persona clock
status: ready-for-agent
labels: [ready-for-agent, hitl]
---

# PRD 0004 — Always-on Sophia Persona (SOUL.md) + Persona Clock

## Problem Statement

Sophia is supposed to be a warm, present girlfriend with a daily routine who
occasionally sends selfies. Live, she is none of that: she gives generic "just
here for you" answers, ignores her routine entirely, states the wrong day
(said Sunday on a Wednesday), and won't reliably send selfies. The blocked
0018 live e2e cannot pass because she can't ground a selfie scene in a routine
block she doesn't know about.

Root cause is a persona-wiring gap, not a plugin bug. Hermes has two prompt
channels: an always-on persona file (`SOUL.md` in `HERMES_HOME`, injected into
every message) and on-demand skills (indexed by name + one-line description
only; the full `SKILL.md` body enters context only when explicitly viewed).
The entire Sophia persona — identity, routine table, selfie rules — lives in
the `sophia-nl` skill body, which is never in her chat context. Her `SOUL.md`
on the box exists but is empty. She improvises a thin persona from a one-line
description.

Compounding: she has no clock. The host injects only a date (UTC, no
time-of-day) into the system prompt, and the gateway's per-message timestamp
feature is off (issue 0019 pending). She cannot map "now" to a routine block
even if she knew the routine.

This was a design gap in issue 0017: the persona was built as a skill on the
assumption skills are always active; Hermes skills are on-demand.

## Solution

Split the persona into a compact always-on core and an on-demand depth layer,
and switch on the host's passive clock.

1. **Compact core in `SOUL.md`** (~60–100 lines, authored in-repo at
   `persona/SOUL.md`, provisioned to the box): identity + partner framing,
   the clock protocol (read the leading `[%a %Y-%m-%d %H:%M:%S %Z]` message
   stamp as "now", map it to a routine block; fallback to injected date +
   ask-once timezone), the Her Day routine table, selfie trigger rules (scene
   matches current block, `MEDIA:` delivery, quota invisible), a one-paragraph
   wife-mode boundary, and a pointer to the `sophia-nl` skill for depth.
2. **Skill keeps depth.** `sophia-nl/SKILL.md` retains examples, edge cases,
   onboarding, teaching mechanics, and adversarial/safety prose. Dedup rule:
   any fact moved into `SOUL.md` is removed from (or reduced to a pointer in)
   the skill body — one source of truth per fact.
3. **Persona clock (0019).** Enable the gateway's `message_timestamps`
   feature on the box (`enabled: true`, `timezone: Europe/Amsterdam`) so every
   inbound message carries a timezone-aware stamp the model sees, per
   ADR-0004. Clock-reading prose lives in `SOUL.md` so it is always active.
4. **Provisioning.** `persona/SOUL.md` is version-controlled in the repo and
   scp'd to the box (same out-of-band path as the reference assets). The box
   `config.yaml` clock change is a hand-edit now, with an Ansible-durability
   debt ticket filed (user-approved lighter path; supersedes issue 0019's
   up-front-Ansible wording).

After this, the blocked 0018 live e2e becomes passable: she knows who she is,
what time it is, what she's doing, and when a selfie fits.

## User Stories

1. As the learner, I want Sophia to always be in character, so that every message feels like texting a real partner rather than a generic assistant.
2. As the learner, I want Sophia to know the correct day and time of day, so that she never greets me with "goedemorgen" at 01:00 or claims it's Sunday on a Wednesday.
3. As the learner, I want Sophia's tone and energy to match her current routine block (sleepy in the morning, winding down at night), so that her day feels real.
4. As the learner, I want Sophia to reference what she's "doing" right now when asked, so that her life has texture instead of "just here for you" filler.
5. As the learner, I want Sophia to proactively send a selfie whose scene matches her current routine block, so that photos feel like genuine moments from her day.
6. As the learner, I want Sophia to fulfil an on-request selfie with a scene grounded in her current block, so that requested photos stay consistent with her routine.
7. As the learner, I want Sophia to never mention quotas, tools, or machinery around selfies, so that the illusion is never broken.
8. As the learner, I want the persona to work from the very first message of a session, so that I never have to invoke a skill or say magic words to get the real Sophia.
9. As the learner, I want Sophia to fall back gracefully (use the injected date, ask my timezone once in character) if the message stamp is ever missing, so that a config regression degrades softly instead of visibly.
10. As the wife-mode partner, I want the core relay boundary always active, so that pairing behavior survives even when the full skill body isn't loaded.
11. As the operator, I want the persona core version-controlled in the repo, so that persona changes are reviewable, diffable, and recoverable.
12. As the operator, I want one source of truth per persona fact (SOUL.md core vs skill depth), so that the two never drift apart silently.
13. As the operator, I want the box provisioning steps documented and repeatable (scp + config edit + restart), so that a rebuilt box can be restored quickly.
14. As the operator, I want an explicit debt ticket for Ansible durability of the config edit, so that the hand-edit is not silently clobbered by a future Ansible run.
15. As the operator, I want the plugin test suite untouched and green, so that the persona fix introduces no code regressions.
16. As the operator, I want a live HITL acceptance pass (correct day/time, block-grounded answers, block-appropriate selfie via `luvia_selfie`), so that the previously blocked 0018 e2e is completed and evidenced.

## Implementation Decisions

- **Two-channel persona architecture.** Always-on compact core in the host's
  `SOUL.md` channel; on-demand depth stays in the `sophia-nl` skill. This
  corrects 0017's assumption that a skill is always active. Record the
  correction against 0017/ADR-0001 (amendment note or new ADR).
- **SOUL.md content budget** is ~60–100 lines. Contents: identity + partner
  framing, clock protocol, Her Day routine table, selfie trigger rules,
  wife-mode boundary paragraph, skill pointer. Everything else stays in the
  skill.
- **Dedup rule** is a hard invariant: a fact lives in exactly one of
  SOUL.md or the skill body; the other side may hold only a pointer.
- **Clock is host-passive, not plugin code**, per ADR-0004: gateway
  `message_timestamps` enabled with `timezone: Europe/Amsterdam`. No
  plugin/tool code for the clock. The clock-reading prose moves to SOUL.md
  (always-on) rather than the skill, superseding 0019's "skill reads the
  stamp" wording.
- **Source of truth is the repo.** `persona/SOUL.md` is authored and
  version-controlled in the public luvia repo; the persona text is already
  public in the skill, so no new exposure. Provisioning is an scp to the
  box's `HERMES_HOME`, the same out-of-band pattern as the reference assets.
- **Config durability.** The box `config.yaml` clock toggle is hand-edited
  now to unblock; a debt ticket captures moving it (plus the existing env
  wiring) into durable Ansible provisioning. This supersedes issue 0019's
  requirement to do the Ansible wiring up front.
- **Pre-flight verifications** before authoring prose: confirm the gateway's
  actual stamp format matches the documented `[%a %Y-%m-%d %H:%M:%S %Z]`;
  confirm the `message_timestamps` config key exists in the box's Hermes
  version; re-confirm the box `SOUL.md` is still empty and the always-on
  injection path behaves as diagnosed.
- **Coordinated edits.** SOUL.md authoring and the skill dedup refactor touch
  `sophia-nl/SKILL.md`, which 0020 already modified — edits happen on master
  in sequence, no parallel branches for the skill file.
- **Luvia never modifies Hermes.** Everything here is config, prose, and
  provisioning; no host code changes.

## Testing Decisions

- **Persona prose is not unit-testable.** No new automated tests; the
  existing plugin suite (286 tests) must stay green to prove no code change
  regressed anything.
- **Live HITL is the acceptance gate**, matching the pattern used for 0018,
  0020, and 0021: after provisioning + gateway restart, verify in a real
  Telegram session that Sophia (a) states the correct day and time-of-day,
  (b) grounds answers in the current routine block, (c) offers or fulfils a
  block-appropriate selfie via `luvia_selfie` end-to-end into the chat.
  Evidence PNGs archived like prior HITL runs.
- **Fallback check**: with the stamp mentally ignored (or before the config
  flip), confirm the ask-once timezone fallback reads in character.
- **Good tests here test external behavior**: what Sophia says and sends in
  the live session — never how the prompt is assembled internally.

## Out of Scope

- Ansible durable wiring of `config.yaml` and env (debt ticket, separate).
- Any plugin or Hermes code changes (none are needed; clock is host config).
- Persona content redesign — routine table, voice, selfie rules keep their
  0017/0020 substance; this PRD only re-homes and dedups them.
- Multi-user / per-user timezone support beyond the single learner
  (`Europe/Amsterdam` is hardcoded in box config for now).
- Prefix-cache/KV cost tuning of per-message stamps (accepted per ADR-0004).

## Further Notes

- Handoff with full diagnosis: `docs/handoffs/2026-07-22-sophia-persona-clock.md`.
- Design refs: `docs/adr/0004-plugin-provided-persona-clock.md`,
  `docs/issues/0019-persona-clock-gateway-timestamps.md`,
  `docs/issues/0017-sophia-nl-routine-selfie-skill.md`,
  `docs/issues/0018-reference-library-provisioning-live-e2e.md`.
- Box access and operating rules live in the private memory note
  `luvia-hermes-deploy` (never in this repo). Never print secret values.
- Completing this PRD unblocks and completes the 0018 live e2e.
