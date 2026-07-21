---
title: "Configurable on-request selfie quota (env ceiling, proactive stays hard)"
status: ready-for-agent
labels: [ready-for-agent]
---

## Parent

PRD 0003 Sophia selfies & daily routine (`docs/prd/0003-sophia-selfies-daily-routine.md`),
amended by ADR 0003 (`docs/adr/0003-configurable-request-selfie-quota.md`).

## What to build

Make the **on-request** selfie cap a configurable ceiling instead of a fixed 3/day, so the
box owner can loosen it for the 0018 live quality/method tuning loop without re-hardcoding.
The **proactive** cap (≤1 per rolling 72h) stays a fixed hard bound and is NOT configurable —
it guards the persona-initiated (LLM-judgment) path per PRD 0003 story 13.

Enforcement architecture is unchanged: the plugin still computes and enforces the cap from
`selfie_log` history (`store.selfie_allowance`); only the request ceiling's *value* becomes
tunable.

- `plugin/store.py`: `REQUEST_LIMIT` reads from env `LUVIA_SELFIE_REQUEST_LIMIT`
  (default `3`). Sentinel `0` disables the request-quota check entirely (unlimited request
  selfies). Invalid/negative/non-int env values fall back to the default `3` (fail-safe, not
  fail-open). Proactive limit + window untouched.
- Test-first (`tests/test_selfie_log.py`), red→green per case, no horizontal slicing.

## Acceptance criteria

- [ ] `LUVIA_SELFIE_REQUEST_LIMIT` unset → request cap is 3/24h (unchanged default edges pass)
- [ ] `LUVIA_SELFIE_REQUEST_LIMIT=10` → request path allows 10/24h, caps at the 11th
- [ ] `LUVIA_SELFIE_REQUEST_LIMIT=0` → request path never caps (unlimited)
- [ ] Malformed env (`"abc"`, `"-1"`, empty) → falls back to default 3 (fail-safe)
- [ ] Proactive cap stays ≤1/72h regardless of the env var (explicit test that the env does
      not affect the proactive bucket)
- [ ] `selfie_allowance` still computes from real `selfie_log` history (no bypass of logging)

## Blocked by

- (none — reopens merged 0012/0016; land before 0018 live testing)
