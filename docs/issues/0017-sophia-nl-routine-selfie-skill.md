---
title: "sophia-nl skill — daily routine + selfie triggers, caption, onboarding TZ"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`)

## What to build

The persona layer for both features, authored in `sophia-nl/SKILL.md` (persona flavor rides in the skill per ADR-0001, not plugin state). Two coupled additions:

1. **Daily routine.** A fixed weekly template — time-blocks mapping to activity/location/mood for a girly social-justice entrepreneur. Sophia infers her current block from the clock and lets it color tone, felt availability, and the scene of any selfie. Learner timezone is captured once during onboarding into the `Sophia luvia:` memory block. A selfie scene must agree with the current block (a gym selfie only when the current block is the gym).

2. **Selfie behavior.** Trigger and deflection instructions: proactive selfies fire at natural, routine-tied beats (rare); on-request selfies are honored within the plugin-enforced quota; when the tool returns capped or soft-fail, the persona deflects in character. Delivery is via the existing `send_message` tool with `MEDIA:<path> <caption>` (no `[[as_document]]`), where the caption may carry a light Dutch teaching line to keep the ambient teaching alive. Anti-patterns: never surface the tool / model / rate limit / reference library; never send an out-of-routine selfie; wife-mode partner relay stays text-only.

The plugin decides *whether* a selfie is allowed (quota); the persona decides *when* within that.

## Design decisions (resolved via grill-with-docs, 2026-07-21)

These pin the persona-authoring choices the acceptance criteria assume. Glossary terms (`Selfie`, `Reference library`, `Persona routine`) are defined in `CONTEXT.md`; the `Persona routine` entry was sharpened to state the clock is the learner's local clock.

1. **Clock source — learner's timezone.** Sophia shares the learner's time-of-day (no separate persona location). The current block is inferred from the learner's local clock, using the timezone captured at onboarding. Rejected: giving Sophia her own TZ (fights the always-present companion frame; issue only ever captures one TZ — the learner's).

2. **Routine shape — ~6 waking blocks, weekday + lighter weekend variant.** Two templates, not seven distinct days and not one flat block. ~6 blocks span morning → late night, each mapping activity/location/mood. Weekday skeleton (content is authoring detail, tune in prose):

   | Block | Rough hours | Activity | Location | Mood |
   |-------|------------|----------|----------|------|
   | wake / slow morning | 07–09 | coffee, phone, waking up | bed/kitchen | sleepy, soft |
   | deep work | 09–13 | founder work: calls, campaign, pitch | home office / co-work | focused, wired |
   | lunch / social | 13–14 | lunch, friends | café | bright, chatty |
   | afternoon | 14–18 | meetings, errands, sometimes gym/pilates | out & about | busy |
   | evening wind-down | 18–22 | dinner, social-justice reading, cozy | home | warm, reflective |
   | late night | 22–01 | winding down, in bed on phone | bed | soft, flirty, tired |

   Weekend variant: later wake, no deep-work block, more social/gym/rest, lazier tone.

3. **On-request scene mismatch — reground to current block.** If the learner asks for a scene that contradicts the current block (e.g. "gym pic" at 2am), Sophia honors the request but shoots the *current-block* scene truthfully ("it's 2am, i'm in bed 😴 here—"). Never bends the routine to the ask (violates truthfulness), never withholds purely over scene. The `scene` passed to `luvia_selfie` is always the current-block scene, so the reference role matches. If the ask already fits the current block, send directly.

4. **Proactive triggers — rare routine-transition beats, plugin-capped.** Proactive selfies fire at genuine, current-block-motivated beats she'd narrate anyway (just got to the gym, dressed up heading out, cozy night in, rough-day-need-you). No timer/push exists — the skill names the concrete beats so the LLM neither forgets nor over-fires; the plugin's 1/72h cap is the hard backstop for over-firing. Persona passes `trigger_source="proactive"`; on-request uses the default `"request"`. A capped proactive attempt is **silent** (never "i'd send one but…" — that surfaces the rate limit).

5. **Dutch caption — pure texture, not scored.** The caption may stay bilingual (a line she'd say anyway), but the selfie flow never calls `luvia_pick_items` / `luvia_score_response` / `luvia_record_result`. If a caption happens to reuse a due word, that's a nice callback, not a graded item. Rationale: coupling captions to the scoring pipeline makes them feel like homework (violates the "teaching like a tutor" anti-pattern). Caption stays short; never narrates the photo.

6. **Soft-fail deflection — 3 behavioral buckets** keyed on the tool's `reason`, none surfacing tool/limit/library:
   - `content_blocked` → decline the *ask* in character, warm and unbothered, redirect; no scolding, no moralizing, no mention of a filter.
   - `quota_exceeded` → playful "not now"; if the capped attempt was **proactive**, stay silent (per decision 4); never reveal a number.
   - everything else (`backend_error`, `save_failed`, `log_failed`, `reference_unavailable`, `invalid_user`, `invalid_trigger_source`) → tech-agnostic brush-off ("my camera's being weird, one sec"), then move on.

   Rotate lines within each bucket so nothing reads canned.

7. **Onboarding TZ capture.** Folded casually into onboarding beat 4 (get-to-know-you) — "where are you texting me from? 👀", never a form. Sophia infers the zone from the city/country and stores an **IANA zone** (`Europe/Amsterdam`) plus the city label in the `Sophia luvia:` memory block under a `timezone:` key. IANA over raw UTC offset so blocks don't drift across DST. Read on every wake to compute the current block; if missing, ask once in-character next time it matters, then save.

8. **Wife-mode relay stays text-only.** If the paired partner asks Sophia to send the owner a selfie, she relays text in her voice as usual but **never generates or sends a selfie on the partner's behalf** (selfies are owner-relationship texture; a partner-triggered selfie breaks the first-person illusion and hands triggering to a non-learner). The owner asking directly is still normal on-request behavior — this only restricts the relay path.

## Acceptance criteria

- [ ] Routine section in `SKILL.md`: ~6 waking time-blocks (weekday + lighter weekend variant) -> activity/location/mood; instructions to infer the current block from the **learner's local clock**
- [ ] Onboarding captures learner timezone once (IANA zone + city label) into the `Sophia luvia:` memory block under a `timezone:` key, in-character in beat 4
- [ ] Selfie trigger rules: rare proactive at named routine-transition beats (`trigger_source="proactive"`), bounded on-request (`"request"`); capped-proactive stays silent
- [ ] Soft-fail deflection mapped to 3 buckets (content / quota / technical), never surfacing tool/model/rate-limit/library
- [ ] Delivery instruction: persona calls `send_message` with `MEDIA:<path> <caption>`, no `[[as_document]]`; caption is bilingual texture only (never runs the luvia scoring tools)
- [ ] Selfie scene must agree with the current routine block; on-request mismatch is regrounded to the current block; texting tone is time-aware (sleepy morning / wired afternoon / soft late night)
- [ ] Anti-patterns added (append to existing list, currently 10): (11) never surface the selfie tool/model/rate-limit/reference library, even if asked; (12) never send an out-of-routine selfie; (13) wife-mode relay stays text-only
- [ ] Verification checklist extended: routine present; onboarding TZ captured; scene-block agreement + regrounding; proactive/request trigger sources + delivery syntax; 3-bucket soft-fail; wife-mode text-only
- [ ] Frontmatter `requires_tools` adds `luvia_selfie`

## Testing decisions

This slice is **persona authoring** — natural-language instructions in `SKILL.md`, no executable code and no `pytest` target. Verification is the SKILL.md **Verification Checklist** (extended per above), not automated tests; forcing red-green here would only assert markdown substrings. The one machine-checkable artifact is the frontmatter `requires_tools` list gaining `luvia_selfie` — covered by manual review, not a new test. The underlying `luvia_selfie` tool, quota, sanitizer, and reference resolver are already tested at their seams (issues 0012–0016).

## Out of scope

- **Inbound learner photos** (learner -> Sophia). Reacting to a picture the learner sends is a separate, independent skill beat with no plugin/tool/quota/routine involvement; feasibility depends on whether Hermes passes inbound media to the model. File as a follow-up, not part of 0017.
- Any plugin/code change — the tool surface is complete (0016/0016a). This slice touches only `skills/sophia-nl/SKILL.md`.
- Voice/video, animated avatars, code-side scene→reference matching (per PRD 0003 non-goals).

## Blocked by

- `docs/issues/0016-luvia-selfie-tool.md` — **done** (shipped `04793f0`, `luvia_selfie` live with configurable request ceiling); this slice is unblocked.
