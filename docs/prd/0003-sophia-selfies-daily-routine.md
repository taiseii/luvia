---
title: Sophia fictional selfies + human-like daily routine
status: ready-for-agent
labels: [ready-for-agent]
---

# PRD 0003 — Sophia Selfies & Daily Routine

## Problem Statement

Sophia (the carrier persona, PRD 0002 engine + sophia-nl skill) texts like a real
girlfriend but has no body and no life. She never sends a photo of herself, and she has no
sense of what she is "doing" right now — so every message lives in a timeless void. A real
partner sends the occasional selfie ("finally at the gym 💪") and her texting is colored by
her day (sleepy in the morning, winding down at night). Without either, the illusion that
makes the persona work — and makes the ambient Dutch teaching land — is thinner than it
should be.

## Solution

Two coupled additions, both riding the existing persona-overlay pattern (ADR-0001: capability
in the plugin, persona flavor in the skill):

1. **Selfies.** A new plugin tool `luvia_selfie(scene, reference_role)` generates an
   in-character photo of Sophia by editing a fixed reference image of her with a scene prompt
   (Black Forest Labs FLUX.2 pro, direct API), then delivers it into the Telegram chat. Sophia
   sends one proactively at natural, routine-tied beats (rare) or on request (bounded), never
   as a bot spamming images. Face stays recognizably Sophia across shots because every selfie
   is one edit-hop off a curated reference of her.

2. **Daily routine.** A fixed weekly schedule authored in the skill gives Sophia a simulated
   life (girly social-justice entrepreneur): time-blocks of activity, location, and mood. She
   infers "what am I doing right now" from the clock and lets it color her tone, her felt
   availability, and — critically — the scene of any selfie she sends (a gym selfie only when
   the current block is the gym).

The machinery stays invisible: Sophia flirts and lives a life; she never surfaces a tool, a
model, a rate limit, or a reference library.

## User Stories

1. As the learner, I want Sophia to occasionally send me a selfie, so that she feels like a
   real person with a body and a life, not a text box.
2. As the learner, I want to be able to ask Sophia for a pic and usually get one, so that the
   relationship feels responsive.
3. As the learner, I want her face to look like the same person every time, so that the
   illusion isn't broken by a stranger's face arriving.
4. As the learner, I want her selfies to match what she's "doing" (gym, bed, café), so that
   they feel spontaneous and situated, not random.
5. As the learner, I want her proactive selfies to be rare and special, so that they land as a
   treat rather than spam.
6. As the learner, I want her selfies to be able to be a little flirty/suggestive
   (lingerie, a shot from bed), so that the girlfriend framing feels real for an adult.
7. As the learner, I never want an explicit/nude image produced, so that the persona stays
   within a hard, non-negotiable content ceiling regardless of how the conversation drifts.
8. As the learner, I want Sophia's texting to feel time-aware (sleepy morning, wired
   afternoon, soft late night), so that talking to her feels like talking across a real day.
9. As the learner, I want her to reference her own day unprompted ("ugh back-to-back calls
   today"), so that she has continuity and interiority.
10. As the learner, I want her selfie scene to never contradict what she just said she's
    doing, so that her life stays internally consistent within a conversation.
11. As the learner, I want the Dutch teaching to keep working around selfies (a selfie can
    carry a Dutch caption), so that the new feature reinforces rather than derails learning.
12. As the maintainer, I want the image backend to be swappable behind one interface, so that
    moving off BFL (or adding FAL later) is a one-file change.
13. As the maintainer, I want all rate limiting enforced in the plugin, not left to the LLM's
    judgment, so that spend and spam are hard-bounded even if the persona "wants" to send more.
14. As the maintainer, I want the reference library to live on the host box and never in the
    repo, so that Sophia's likeness is never published to a public GitHub.
15. As the maintainer, I want the reference set fixed (never auto-grown from generated output),
    so that identity never drifts from editing edits-of-edits.
16. As the maintainer, I want per-image metadata so the persona can pick the right reference
    for a scene, so that a full-body gym selfie starts from a full-body reference, not a
    face-crop.
17. As the maintainer, I want reference images fed to the API inline (base64), so that nothing
    is uploaded to a public URL or third-party host.
18. As the maintainer, I want every generated selfie logged with a timestamp per learner, so
    that quota windows are computed from real history and future analytics are possible.
19. As the maintainer, I want the daily routine to be persona flavor in the skill, not plugin
    state, so that a different carrier persona brings its own life without a schema change.
20. As the maintainer, I want the content sanitizer to be a hard rule, not a persona dial, so
    that no onboarding choice or conversation can raise the ceiling past no-nudity.
21. As the maintainer, I want the selfie tool to degrade gracefully when the backend or
    delivery fails, so that a failed generation never breaks the conversation or leaks an error
    to the learner as Sophia.
22. As the learner in wife mode, I want the partner relay to remain text-only, so that the
    selfie feature never becomes an unexpected image channel from a third party.

## Implementation Decisions

- **New plugin tool `luvia_selfie(scene, reference_role)`** in the `luvia_*` surface. `scene`
  = free-text description of the shot Sophia wants; `reference_role` = which reference to edit
  from (`canonical_face` default, or a pose role). Generates the image and saves it to a box
  path, returning that path; on any failure returns a soft-fail the persona can absorb in
  character (never raises to the chat).
- **Delivery — shape A, confirmed on the box (Q8 resolved).** No custom Telegram code. The
  existing `send_message` tool (already in Sophia's `requires_tools`) delivers the file: image
  extensions default to inline `send_photo`, and the `MEDIA:<path> <caption>` syntax attaches a
  native photo caption (Telegram 1024-char cap). Contract: `luvia_selfie` returns the path →
  Sophia calls `send_message` with `MEDIA:<path> <caption>`, no `[[as_document]]` (that flag
  would force a file attachment instead of an inline photo). The caption channel carries the
  optional Dutch teaching text on the selfie itself.
- **Backend: BFL FLUX.2 pro, direct API**, key read from `FLUX_API` env (`bfl_…`). Explicitly
  NOT the Hermes-native FAL `image_generate` tool — that needs a `FAL_KEY` the box does not
  have. Backend sits behind a thin generate-image interface (one method: edit reference + scene
  prompt → image bytes) so it is swappable.
- **Consistency via a fixed reference library, persona-selected.** The LLM picks
  `reference_role`; no code-side fuzzy matching. Every selfie is a single edit off one curated
  reference → face stays anchored. Portrait is the default/fallback role.
- **Reference library: 5 curated images** (`potrait.jpg` canonical face + 4 pose shots),
  living ON THE BOX ONLY, never the repo. `assets/sophie/` added to `.gitignore` as a guard.
  Library is fixed — never auto-grown from generated output (drift avoidance). Growing it later
  means hand-curating new images, still fixed.
- **Reference metadata: `manifest.json`** colocated with the images on the box. Per-image
  schema: `{file, role (canonical_face|pose), framing (portrait|half|full), setting, tags[],
  description, default}`. Plugin reads the assets directory from env `LUVIA_SOPHIA_ASSETS`.
  Not a DB table — 5 static rows. Named "reference manifest" to disambiguate from the existing
  content manifest.
- **Reference fed to BFL inline as base64**; result downloaded, delivered, never published to a
  URL or public host.
- **Content policy — hard ceiling, not a dial.** Suggestive-but-clothed allowed
  (lingerie/underwear, bedroom, flirty framing). Full nudity, exposed genitals/breasts, and
  explicit acts hard-blocked by a tool-side prompt sanitizer (runs before any API call) AND
  BFL's own `safety_tolerance`. Persona is adult fiction; the reference set is of an adult. No
  persona/onboarding setting can raise this ceiling.
- **Rate limits, plugin-enforced:** proactive selfies ≤ 1 per rolling 72h; on-request ≤ 3 per
  day. Enforced in Python from logged history, never trusted to LLM judgment. When capped, the
  tool returns a "capped" result the persona deflects in character.
- **Schema change: new `selfie_log` table** in the Phase 1 SQLite schema — one row per
  generated selfie, keyed by learner, with timestamp and trigger source (proactive|request).
  Quota windows computed from it (mirrors how pacing reads trailing windows).
- **Triggers:** request + proactive. Proactive fires at natural relationship beats tied to the
  current routine block. The persona decides *when* within the plugin-enforced quota; the
  plugin decides *whether* it's allowed.
- **Daily routine: fixed weekly template authored in `SKILL.md`** — time-blocks →
  activity/location/mood. NOT plugin DB state (ADR-0001: persona flavor rides in the skill).
  The LLM infers the current block from the clock. Learner timezone captured once during
  onboarding into the `Sophia luvia:` memory block. Routine colors tone, felt availability, and
  selfie scene context; a selfie scene must agree with the current block.
- **Skill changes:** routine template section, selfie trigger/deflection instructions, caption
  behavior (a selfie may carry a light Dutch caption to keep teaching alive), onboarding
  timezone capture, and anti-pattern additions (never surface the tool/rate-limit; never send
  an out-of-routine selfie).

## Testing Decisions

- **Primary seam is the tool function**, per the existing `luvia_*` pattern: call
  `luvia_selfie(...)` directly against a temp SQLite db, with the BFL client and Telegram
  delivery **injected/monkeypatched** so tests never touch the network. Assert quota
  enforcement, reference resolution, sanitizer application, `selfie_log` writes, and the
  returned/soft-fail shapes.
- **Prompt sanitizer — pure function seam.** Table-driven: suggestive-but-clothed prompts pass
  through unchanged; nudity/explicit prompts are rejected. No db, no network. This is the
  security-critical seam and gets the most cases.
- **Reference-manifest resolver — pure function seam.** Temp assets dir + `manifest.json` →
  assert `role` → file resolution and portrait fallback when a role is missing/unspecified.
- **Quota boundaries — via the tool seam**, driving `selfie_log` rows across time windows to
  assert the proactive-1/72h and request-3/day edges (mirrors `test_pacing` /
  `test_plan_today` window-driven style).
- **Graceful degradation — via the tool seam.** Injected backend/delivery raising → assert the
  tool returns a soft-fail result and writes no `selfie_log` row (a failed generation must not
  consume quota).
- Good tests assert externally observable behavior (tool return payloads, `selfie_log` rows,
  quota decisions, sanitizer verdicts) — never internal call order or private state.
- Prior art: `test_record_result.py`, `test_pacing.py`, `test_plan_today.py` (temp-db +
  window-driven), `test_score_response.py` (pure deterministic function).

## Out of Scope

- **Growing/auto-curating the reference library** from generated output — fixed set only this
  PRD.
- **Code-side scene→reference matching** — the LLM picks the role; no fuzzy matcher.
- **FAL / Hermes-native `image_generate` path** — documented as the rejected alternative, not
  built.
- **Voice/video, animated avatars, image editing beyond single-reference scene edits.**
- **Public hosting / URL delivery of any image** — inline base64 in, direct delivery out.
- **Multi-persona routine framework** — routine is authored in sophia-nl's skill only; the
  generalization is left implicit in ADR-0001, not built as shared infra.
- **Wife-mode image relay** — the partner relay stays text-only.

## Further Notes

- **Delivery — resolved (shape A).** Box probe confirmed `send_message_tool.py` already sends
  media via `bot.send_photo` (inline) for image extensions, falling back to `send_document`
  only under the `[[as_document]]` directive. `send_message` is already in Sophia's tool set,
  and its `MEDIA:<path> <caption>` syntax gives a native captioned photo. So `luvia_selfie`
  owns generation only; the persona delivers via the existing tool. The injected-delivery test
  seam still stands (tests stay offline), but no bespoke Telegram code is built.
- **ADR candidate.** The BFL-direct-integration + fixed-reference-library-no-drift decision is
  hard to reverse, surprising to a future reader, and the result of a real trade-off (rejected
  FAL/native path; rejected growing-library for drift reasons). Worth an ADR
  (`docs/adr/0002-…`) once implementation confirms the delivery shape.
- **Verified facts this PRD relies on:** `FLUX_API` in `.env` is a Black Forest Labs key
  (`bfl_…`, not FAL); `.env` is gitignored and never committed; `assets/sophie/` is untracked
  and never on GitHub; the reference images exist locally (portrait + 4 poses). BFL FLUX.2 pro
  supports reference-image editing and server-side `safety_tolerance` moderation.
