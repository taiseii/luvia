# Plan — Ship Sophia selfies + daily routine (0016a → 0017 → 0018)

Ships the **already-built** selfie capability live. The richer image expansion
(POV/object `luvia_image`, multi-output outfit try-on, text→image backend, seed/aspect
knobs, rich per-pose metadata) is ring-fenced as **PRD 0004** — not in scope here.

Sequencing is strict: **0016a → 0017 → 0018**. 0018 is HITL (human curation, real spend,
live Telegram) and blocks on both predecessors. Nothing parallelizes.

## Resolved decisions (grill 2026-07-21)

- **Clock:** Hermes injects no ambient time. The gateway CAN prepend each inbound message
  with `[Wkd YYYY-MM-DD HH:MM:SS TZ]` (`gateway/message_timestamps.py`) but it defaults
  OFF and the box is `Etc/UTC`. Enable it + pin tz on the box (see 0018). Persona reads the
  prefix as "now". No plugin clock tool, no shell `date`. (Config-reversible → no ADR.)
- **Capability split:** her selfies (identity-anchored edit) vs world/object images
  (not her) are two capabilities. Only selfies ship now. World/object → PRD 0004.
- **Reference reality:** `reference_role` has two useful values — `canonical_face`, `pose`.
  4 pose files are one undifferentiated role; manifest framing/setting/tags are inert in
  shipped code. References are 1024² half-body. No true full-body — frame as mirror /
  reflection / partial-body selfies (natural human framing).
- **Request quota:** configurable ceiling (ADR 0003), not fixed. Proactive stays hard ≤1/72h.
- **Method/quality tuning surface:** `scene` prompt + `reference_role` only. `safety_tolerance`
  pinned at 2 (max; stricter-only). No seed/aspect on shipped seam (→ 0004 if joint tuning
  needs it).

## 0016a — Configurable request quota (plugin, TDD)

Reopens merged 0012/0016. Small, test-first.

- `plugin/store.py`: `REQUEST_LIMIT` from env `LUVIA_SELFIE_REQUEST_LIMIT` (default 3);
  sentinel `0` → skip the request-quota check (unlimited). Proactive path untouched.
- `tests/test_selfie_log.py`: keep the 3/day default edges; add cases for a raised limit
  and for `0` = unlimited (request path never caps; proactive still caps).
- Red → green per case; no horizontal slicing.

## 0017 — sophia-nl skill prose (skill-only, no code)

Author into `skills/sophia-nl/SKILL.md`. Not TDD (prose); verify via the skill's
Verification Checklist. Add `luvia_selfie` to `requires_tools` in the frontmatter.

### Routine section (weekly template, Amsterdam-local, mood arc sleepy→wired→soft)

Weekday (Mon–Fri), 8 blocks:
- 07:00–09:00 wake/matcha/get-ready — home — sleepy-soft, slow — bed/getting-ready/cozy mirror
- 09:00–12:30 deep work/calls — co-work or desk — focused, terse quick replies — desk+coffee, rare
- 12:30–13:30 lunch — café/friends — bright, chatty — café/food/outfit
- 13:30–17:30 meetings + community/activism — out — wired, busy — out-and-about, rare
- 17:30–19:00 movement (pilates Mon/Wed/Fri, run Tue/Thu) — studio/park — energized — gym mirror/post-workout/activewear
- 19:00–21:00 dinner — home or out — relaxed, social, flirty — dressed-up/mirror
- 21:00–00:30 wind-down/skincare/tv — home/bed — soft, affectionate, intimate — cozy/bed/loungewear/lingerie (suggestive-clothed)
- 00:30–07:00 asleep — mostly unavailable, groggy short replies; **repeated pokes wake her**; no proactive

Weekend: Sat = slow morning, brunch, errands, evening social/night out (dressed-up, flirty).
Sun = reset: self-care, meal-prep, reading, early night (soft, homey, reflective).

Instruction: read the message-timestamp prefix → infer current block → let it color tone,
felt availability, and any selfie scene.

### Onboarding tz capture

Casual get-to-know-you beat ("where you texting me from btw? 🌍") → store `tz:` in the
`Sophia luvia:` memory block. Operative clock stays the stamp; tz is continuity/future-proofing.

### Selfie behavior

- On-request → `luvia_selfie(trigger_source='request')`; honor within the (configurable) cap.
- Proactive → in-conversation-only, rare, routine-tied beat → `trigger_source='proactive'`
  (plugin caps ≤1/72h). No scheduled/out-of-blue (not built).
- `trigger_source` discipline: asked = request; unprompted = proactive.
- Scene must agree with the current block. Out-of-block request → redirect to current
  reality, never fabricate an out-of-block shot, never claim old photos.
- `scene` free-text carries outfit/activity/setting; pick `canonical_face` (face) or `pose` (body-ish).
- Deliver via `send_message MEDIA:<path> <caption>`, no `[[as_document]]`. Caption short,
  in-voice; a light Dutch line **sometimes** (tied to daily plan/due words, glossed once) — not every pic.

### Deflection (from soft-fail `reason`, never expose machinery)

- `quota_exceeded` / `content_blocked` → playful boundary she owns ("greedy 😏 later" / "lol no, behave").
- `backend_error` / `save_failed` / `reference_unavailable` → soft camera-pivot ("ugh my camera's being weird, one sec") then move on.

### Anti-patterns added

- Never surface the selfie tool/model/rate-limit/reference-library/"generate".
- Never send a selfie contradicting the current block.
- Never claim old photos / a photo library.
- Wife-mode partner relay stays text-only — never send/relay an image for/from the partner.

## 0018 — Provisioning + live e2e (HITL)

On the box, out-of-band (scp/rsync over Tailscale — never git; `assets/sophie/` gitignored):
- Transfer `assets/sophie/` (5 jpgs + `manifest.json`) verbatim to `LUVIA_SOPHIA_ASSETS`.
- **Manifest edit:** set exactly one pose row `default: true` (deterministic `pose` resolution).
  Pick during tuning — the pose that consistently wins. Skip refining the other (inert) metadata.
- Env: `FLUX_API` (bfl_ key), `LUVIA_SOPHIA_ASSETS`, `LUVIA_SELFIE_REQUEST_LIMIT` (loose for tuning).
- **Box `config.yaml`:** add `timezone: Europe/Amsterdam` and `gateway.message_timestamps.enabled: true`.
- **Probe:** `scripts/selfie_probe.py` — args scene + role, fires `luvia_selfie(trigger_source='request')`,
  prints saved path. Iterate scene/reference together, eyeball likeness/realism.
- Verify: real selfie generates + delivers into Telegram via `send_message MEDIA:` — face recognizably
  Sophia; `selfie_log` row written; quota behaves; library stays fixed (no generated output fed back).
- Feed tuning findings back: winning scene patterns → 0017 phrasing guidance; winning pose → default:true.

## PRD 0004 (parked — do not build now)

World/object/POV `luvia_image` (text→image, not her, separate/looser quota); multi-output
outfit try-on; richer reference taxonomy + resolver that consumes manifest metadata;
seed/aspect backend knobs.
