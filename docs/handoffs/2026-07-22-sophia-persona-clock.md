# Handoff: always-on Sophia persona (SOUL.md) + persona clock (0019)

## Focus for next session
Fix the live-discovered "routine not working" bug, then complete the blocked 0018 live e2e.
Design is **already brainstormed + approved** (see below). Next step = write the design doc,
then `writing-plans`, then implement.

## What just shipped (done, pushed, live on box)
- 0020 role-aware selfie POV — `docs/issues/0020-role-aware-selfie-pov.md` (status: done)
- 0021 multi-reference anchors + pinned seed — `docs/issues/0021-multi-reference-seed-identity-fidelity.md` (status: done)
  - Code commits pushed to `origin/master`: `a3d9bd6` (feat), `f2411fa` (close), plus `b174a08` (0020 close).
  - 286 tests green. Backend/manifest/tool details in the commits + issue files — don't re-derive.
- HITL evidence PNGs: local `docs/hitl/0020/`, `docs/hitl/0021/` (gitignored via `docs/hitl/**/*.png`);
  also archived on box at `/home/hermes/.hermes/luvia-hitl/`.

## 0018 provisioning state (mostly done)
Issue: `docs/issues/0018-reference-library-provisioning-live-e2e.md`. On the box already:
- Refs library: `/home/hermes/.hermes/sophie-refs/` — 5 role PNGs + `manifest.json` (real per-role fields). Validated on-box: loads, resolves canonical_face/poses, unknown->canonical_face fallback, anchors=[canonical_face].
- Env on box: `FLUX_API` (set — never print its value) and `LUVIA_SOPHIA_ASSETS` (points at the refs dir) are both present in the gateway's env file.
- Plugin updated to 0021 in place (scp'd 3 files: image_backend.py, reference_manifest.py, tools.py), byte-compiled OK, gateway restarted, full plugin imports clean under venv.
- **BLOCKED**: the live selfie-into-Telegram e2e cannot pass until the persona bug below is fixed
  (she won't reliably call `luvia_selfie` and can't ground scenes without the persona/clock).

## THE BUG (root cause, fully diagnosed)
Symptom: persona gives generic "just here for you" answers, ignores her routine, states the
wrong day (said Sunday; real day Wednesday 2026-07-22).

Root cause = **persona-wiring gap, not a plugin-code bug**. Hermes has two prompt channels:
- Always-on persona: `SOUL.md` / `.hermes.md` / `AGENTS.md` in `HERMES_HOME`, injected every
  message (`agent/system_prompt.py:392`). **`/home/hermes/.hermes/SOUL.md` exists but is EMPTY (0 lines).**
- On-demand skills: indexed by name+description only; full `SKILL.md` body loads via `skill_view`
  when invoked (`agent/system_prompt.py:294-309`).

The entire Sophia persona (routine table, selfie machinery) lives in the `sophia-nl` SKILL.md
body, which is NOT in her chat context — she improvises a thin persona from the one-line skill
description. Compounding: no time-of-day — `message_timestamps` is OFF (0019 pending), host
injects date-only UTC (`system_prompt.py:504-511`, format `%A, %B %d, %Y`, no time).

This is a design gap in 0017 (persona built as a skill, assumed always-active; Hermes skills
are on-demand).

## Approved design (from brainstorming — ready to write up)
1. **Compact core + skill depth split.** `SOUL.md` (always-on) holds: identity + partner
   framing, clock protocol (read leading `[%a %Y-%m-%d %H:%M:%S %Z]` stamp as "now" -> map to
   routine block; fallback to injected date + ask-once timezone), the Her Day routine table,
   selfie trigger rules (scene matches current block, `MEDIA:` delivery, quota invisible),
   wife-mode boundary (one para), pointer to the skill. Target ~60-100 lines.
   The `sophia-nl` skill keeps depth (examples, edge cases, adversarial/safety prose).
   **Dedup rule:** anything moved into SOUL.md is removed/reduced-to-pointer in the skill body
   so there's one source of truth per fact.
2. **Source of truth = repo, provisioned to box.** Author `persona/SOUL.md` in the public luvia
   repo (version-controlled). Provision = scp to `/home/hermes/.hermes/SOUL.md` (same out-of-band
   path as assets). Persona text is already public in the skill, so no new exposure.
3. **0019 clock:** box `config.yaml` -> `gateway.message_timestamps.enabled: true`,
   `timezone: Europe/Amsterdam`; restart gateway; clock-reading prose lives in SOUL.md (always-on).
   Design ref: `docs/adr/0004-plugin-provided-persona-clock.md`, `docs/issues/0019-persona-clock-gateway-timestamps.md`.
   **Folded decision:** hand-edit `config.yaml` now to unblock + file an Ansible-durability debt
   ticket (user chose the lighter repo-provisioned path over up-front Ansible). Confirm still OK.
4. **Verification (live HITL):** after provisioning + restart, confirm she (a) states correct
   day/time-of-day, (b) grounds answers in the current routine block, (c) offers/sends a
   block-appropriate selfie via `luvia_selfie` -> completes the blocked 0018 e2e.
5. **Testing:** persona prose isn't unit-testable; keep plugin suite green (no code change); live
   HITL is the acceptance gate.

Note: SOUL.md and 0019 both touch `skills/sophia-nl/SKILL.md` — coordinate edits (0020 already
merged there).

## Next steps (resume here)
1. Finish `superpowers:brainstorming`: write design doc to
   `docs/superpowers/specs/2026-07-22-sophia-persona-clock-design.md`, commit, spec self-review,
   user review gate.
2. `superpowers:writing-plans` -> implementation plan.
3. Implement: author `persona/SOUL.md`, refactor `skills/sophia-nl/SKILL.md` (dedup), box
   `config.yaml` clock edit, provision SOUL.md to box, restart, live e2e.
4. Optionally split into issues via `to-issues` (persona-wiring correction + 0019 clock) and/or
   reconcile with 0017/ADR.

## Box access
Box host, tailnet IP, SSH alias/key, venv path, gateway service, and plugin/skill install
quirks are in the **private** memory note `luvia-hermes-deploy` (under `~/.claude/.../memory/`,
NOT in this public repo). Read that for access. Operating rules:
- Gateway reads its env from an `EnvironmentFile`; restart the gateway service (root) after
  config/plugin changes.
- Plugin is a subdir install: update = scp the changed files or remove+reinstall, NOT
  `hermes plugins update`.
- `sophia-nl` skill is raw-URL installed (source=url, enabled).
- **NEVER print `FLUX_API` or other secret values — env var NAMES only.**

## Suggested skills for next session
- `superpowers:brainstorming` (resume — was mid-flow; terminal state is writing the design doc)
- `superpowers:writing-plans` (after design doc approved)
- `superpowers:test-driven-development` or `tdd` (if any code lands; mostly prose here)
- `superpowers:executing-plans` (to run the plan)
- `claude-mem:mem-search` / memory `luvia-hermes-deploy`, `luvia-project-state` (box + project context)

## Local git state
- On `master`, pushed through `f2411fa`. Untracked: `docs/plans/` (pre-existing, not mine).
- Working tree otherwise clean.
