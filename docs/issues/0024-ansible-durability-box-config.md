---
title: "Debt: durable Ansible wiring for box config.yaml + env"
status: backlog
labels: [backlog, debt]
---

## Parent

PRD 0004 Always-on Sophia persona + persona clock
(`docs/prd/0004-sophia-always-on-persona-clock.md`).

## What to build

The box currently carries hand-edited state that a future Ansible run (or box
rebuild) would clobber or lose:

- `config.yaml`: `gateway.message_timestamps.enabled: true`,
  `timezone: Europe/Amsterdam` (0019 hand-edit)
- Gateway env file: `FLUX_API`, `LUVIA_SOPHIA_ASSETS`
- Provisioned artifacts: persona file (SOUL.md), reference library
  (`sophie-refs/`), installed luvia plugin + sophia-nl skill

Move these into durable, repeatable provisioning (Ansible or equivalent) so a
rebuilt box restores the full Sophia stack without manual steps. Secrets stay
out of the repo (vault or injected), per existing rules — never print values.

Deliberately deferred: user chose the lighter hand-edit-now path to unblock
0019/0023 (folded decision in PRD 0004, superseding 0019's up-front-Ansible
wording).

## Acceptance criteria

- [ ] One durable provisioning run restores config.yaml keys, env vars, and
      provisioned artifacts on a clean box
- [ ] No secret values in the repo
- [ ] Hand-edited state on the current box matches the durable definition
      (no drift)

## Blocked by

- 0019 and 0023 (captures their hand-edited state once landed)
