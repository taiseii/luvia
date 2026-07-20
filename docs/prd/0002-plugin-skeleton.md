---
title: Luvia plugin skeleton
status: ready-for-agent
labels: [ready-for-agent]
---

# PRD 0002 — Plugin Skeleton

## Problem Statement

Luvia's design is fully specified but no runtime exists: there is no database schema in
place, no scheduler, no way to record a practice result, and nothing the carrier persona
(sophia) can call. Until the plugin exists, seeded content (PRD 0001) has nowhere to live
and the learner cannot practice at all.

## Solution

The Luvia Hermes plugin: a Python plugin package exposing the `luvia_*` tool surface over a
SQLite database, containing the swappable scheduler (SM-2 first), the mode-aware content
picker, the pacing band, and deterministic scoring. Deployable to the Hermes server as a
self-contained package from this repo. The ambient skill overlay and cron wiring come later;
this PRD delivers the engine they will drive, verified end-to-end through the tool surface.

## User Stories

1. As a learner, I want my practice results recorded and my items rescheduled in one atomic step, so that no review is ever logged without its scheduling effect.
2. As a learner, I want grading with Again/Good/Easy, so that review effort maps to familiar spaced-repetition behavior.
3. As a learner, I want an "Already knew" option on first encounter that fast-tracks the item to a ~month interval, so that my existing A2 vocabulary sweeps through without tedium.
4. As a learner, I want a guaranteed daily allotment of genuinely new items governed by the pacing band (35–70/week, start 50), so that I am exposed to new words every day regardless of review backlog.
5. As a learner, I want the pacing band to ratchet up when my trailing recall and completion are strong, so that the system speeds up to my pace.
6. As a learner, I want the pacing band to back off when recall drops or I skip days, so that I'm not buried after a bad week.
7. As a learner, I want daily review load capped with overflow spilling forward, so that one missed day never creates a guilt backlog.
8. As a learner, I want my progress queryable (recall rate, sweep progress, band position, due counts), so that I can see whether this is working.
9. As a learner, I want all my state in one SQLite database on the server, so that scheduled runs and fresh sessions always see current state without chat memory.
10. As a carrier persona, I want to fetch a small ambient micro-batch of items, so that I can weave practice into conversation at a natural moment.
11. As a carrier persona, I want to fetch a due-review batch for review mode, so that I can run a button-graded flashcard flow.
12. As a carrier persona, I want to record an implicitly graded ambient exchange (including comprehension breaks), so that adaptation signals accumulate without visible rubrics.
13. As a carrier persona, I want a daily plan (due load, new intake, suggested mode balance), so that I can pace the day's touches sensibly.
14. As a carrier persona, I want deterministic scoring of typed answers (exact/fuzzy) before any LLM judgment, so that grading is cheap and consistent.
15. As a carrier persona, I want to onboard the learner (create user, capture interests and contexts), so that content tagging and phrase seeding have real data.
16. As a maintainer, I want the scheduler behind a single interface with algorithm parameters stored per item as opaque state, so that SM-2 can be swapped for FSRS with one migration and zero data loss.
17. As a maintainer, I want every review event logged in full (grade, timestamp, latency), so that a future FSRS optimizer has complete training history.
18. As a maintainer, I want sessions grouped as gap-based bursts with a mode column, so that ambient, review, and conversation activity are analyzable without user-facing ceremony.
19. As a maintainer, I want the plugin to follow Hermes conventions (manifest, snake_case `luvia_*` tool names), so that it loads like any first-class plugin.
20. As a maintainer, I want a deploy script that syncs the plugin and skill directories to the server checkout, so that this repo stays canonical and Hermes is never forked.
21. As a maintainer, I want multi-user-ready keys (learner state keyed by user and item), so that adding a second learner never requires a schema rewrite.

## Implementation Decisions

- Full SQLite schema from the spec ships in this PRD: users, languages, content items,
  item tags, learner items (composite user+item key, generic columns plus
  `scheduler_state_json`), sessions (mode: ambient/review/conversation, gap-closed),
  session events (grade enum, latency, comprehension-break flag), method profiles, and the
  dormant experiment tables.
- Scheduler contract (decision-precise, from the design session):

  ```python
  def schedule(item_state: SchedulerState, grade: Grade, now: datetime) -> tuple[SchedulerState, datetime]
  # Grade = again | good | easy | already_knew  (already_knew: first encounter only)
  ```

  SM-2 variant implements it first; all algorithm parameters live inside the opaque
  scheduler state, never as schema columns.
- Fast-track: `already_knew` on first encounter jumps to a ~30-day interval with an ease
  bump; such sweeps do not consume the pacing band.
- Pacing band: 35–70 genuinely-new items/week, start 50; weekly ratchet on a trailing
  two-week window (recall ≥85% and daily completion → up 5–10; recall <70% or 3+ skipped
  days → down); binding constraint is the review-load ceiling (~100 touches/day) with
  overflow spilling forward; new intake never starved to zero.
- Recording is atomic: one tool call both logs the event and updates scheduling state
  (the persona must not be trusted to make two calls).
- Tool surface (Phase 1): setup, plan-today, pick-items (mode-aware), record-result,
  score-response, set-method, stats. Snake_case with `luvia_` prefix per verified Hermes
  convention; declared in the plugin manifest.
- Completion metric: share of due items cleared by end of day (not per-session).
- Latency is trusted from button-tap flows, treated as noise from typed chat.
- Method profiles load from YAML into the profiles table; Phase 1 ships `frequency_srs`
  and `communicative_hybrid` (informal register, adaptive language mix).
- Deterministic scoring first (normalized exact match, then fuzzy threshold); LLM judgment
  is the persona's job, outside this plugin.
- Database file lives in the Hermes home directory on the server; the plugin reconstructs
  all state from it at call time (no reliance on chat context, per cron constraint).
- Per ADR-0001: no persona coupling anywhere in the plugin — all persona behavior lives in
  the (out-of-scope) skill overlay.

## Testing Decisions

- Tests exercise the tool surface as the primary seam: call tool functions directly against
  a temp SQLite database seeded with fixtures; assert returned payloads and resulting rows.
  No Hermes runtime in tests; the manifest is validated statically.
- Scheduler tested table-driven through its public interface: grade sequences → expected
  interval progressions, fast-track jump, state opacity (a second scheduler implementation
  can be registered in tests to prove swappability).
- Pacing tested as a pure function over synthetic review histories: ratchet up, ratchet
  down, floor, ceiling-binding, overflow spill.
- Good tests here assert externally observable behavior (tool outputs, due dates, band
  values) — never internal call order or private state.
- Prior art: none in-repo yet (first runtime code); the exploration scripts set the
  fixture-driven style.

## Out of Scope

- The ambient skill overlay (SKILL.md content, weaving prompts, persona instructions) and
  Chronos cron wiring — next PRD after the engine exists.
- Voice (transcription grading, TTS listening), articles, method mixing, adaptive
  language-mix logic beyond logging its input signals.
- Experiment tooling (tables ship dormant), FSRS implementation (interface only).
- The Hermes server backup-role change (deployment concern, tracked in the spec).
- Seed data production (PRD 0001).

## Further Notes

Verified Hermes integration facts this PRD relies on: plugins are Python packages with a
YAML manifest and prefixed snake_case tools; the clarify tool provides inline grading
buttons on Telegram; cron runs arrive with no chat memory. The plugin must therefore be
fully state-reconstructing from SQLite on every call.
