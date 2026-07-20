---
title: "Deploy script: sync plugin and skill dirs to the Hermes server checkout"
status: needs-human
labels: [hitl]
---

## Parent

PRD 0002 — Plugin Skeleton (`docs/prd/0002-plugin-skeleton.md`)

## What to build

A deploy script that syncs the plugin and skill directories from this repo to the Hermes
server checkout, so this repo stays canonical and Hermes is never forked. The plugin must
land where Hermes discovers plugins and load like any first-class plugin.

HITL: the target path on the server needs confirmation, and the final acceptance step —
the plugin actually loading in the live Hermes instance — requires a human at the server.
The script itself, with a dry-run mode, can be built without access.

## Acceptance criteria

- [ ] Script syncs the plugin package (and skill directory, once it exists) to a configurable server checkout path
- [ ] Dry-run mode prints what would sync without touching the server; covered by a test against a local target directory
- [ ] Idempotent: re-running with no changes syncs nothing
- [ ] Human-verified: after a real deploy, Hermes loads the plugin and the `luvia_*` tools are callable

## Blocked by

- 0001-walking-skeleton-schema-setup
