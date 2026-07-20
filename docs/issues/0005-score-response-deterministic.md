---
title: "luvia_score_response: deterministic scoring of typed answers"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0002 — Plugin Skeleton (`docs/prd/0002-plugin-skeleton.md`)

## What to build

Deterministic scoring of typed answers before any LLM judgment, so grading is cheap and
consistent: `luvia_score_response` takes the learner's typed answer and the expected
answer(s), normalizes, tries exact match, then falls back to a fuzzy threshold. LLM
judgment of ambiguous answers is the carrier persona's job, outside this plugin — the tool
just reports the deterministic verdict so the persona knows when to escalate.

Pure scoring function wrapped by the tool; no scheduling side effects.

## Acceptance criteria

- [ ] Normalized exact match handles case, surrounding whitespace, and punctuation noise
- [ ] Fuzzy pass accepts near-misses within the threshold and rejects beyond it; threshold cases covered table-driven
- [ ] Verdict distinguishes exact, fuzzy, and no-match so the persona can decide when to apply LLM judgment
- [ ] Tool declared in the manifest; calling it has no effect on scheduling state
- [ ] Multiple accepted answers per item supported (e.g. synonymous translations)

## Blocked by

- 0001-walking-skeleton-schema-setup
