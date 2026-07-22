# Ambient-first learning via a persona overlay, not a teacher interface

Luvia was originally specced as a teacher-style Hermes extension: slash-command sessions
(`/luvia today`), a rigid session state machine, and Anki-style drills. We decided instead
that the primary mode is **ambient practice**: a persona-agnostic overlay skill that rides
on whatever companion persona is active (sophia first), weaving Dutch practice into natural
Telegram conversation at randomized moments (10:00–24:00) and grading implicitly from the
learner's replies. Explicit review mode (inline grading buttons via Hermes's clarify tool)
survives only as the daily SRS-load workhorse, and the session state machine survives only
inside explicit modes.

Why: the learner's goal is casual communication with Dutch-speaking friends; a teacher
persona and scheduled drills were judged the wrong register and the wrong adherence model.
Trade-off accepted: ambient throughput is far lower than flashcard throughput, so review
mode remains mandatory daily for the pacing band (35–70 new items/week) to be achievable.

Consequence worth recording: Luvia must never hard-depend on any one persona — all persona
coupling lives in skill instructions, all state and scheduling lives in the plugin.

**Amendment (2026-07-22, PRD 0004).** "All persona coupling lives in skill instructions"
assumed skills are always in context. They are not: Hermes indexes skills by name +
description only and loads the body on demand, so a persona built solely as a skill is
absent from most turns (live symptom: generic answers, wrong day, no routine). Corrected
model is **two channels**: a compact always-on core (identity, clock protocol, routine
table, selfie trigger rules, wife-mode boundary) lives in the host's per-message persona
file (`SOUL.md`, repo-authored at `persona/SOUL.md`, provisioned to the box), while the
skill keeps on-demand depth (onboarding, teaching mechanics, procedures, examples). One
source of truth per fact between the two. State and scheduling still live in the plugin;
issue 0017 was built on the old assumption and is corrected by issues 0022/0023.
