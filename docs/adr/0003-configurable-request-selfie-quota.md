# Request-selfie quota is a configurable ceiling, not a fixed hard bound

PRD 0003 (story 13) specified all selfie rate limiting as a plugin-enforced **hard**
bound — including on-request selfies at 3/day. We are softening the *request* path:
`REQUEST_LIMIT` reads from env `LUVIA_SELFIE_REQUEST_LIMIT` (default `3`), and a sentinel
(`0`) disables the request-quota check entirely. The **proactive** cap (≤1/72h) stays a
fixed hard bound and is NOT configurable.

Why: on-request selfies are learner-initiated and self-throttling, and the box is a
single-owner deployment paying its own BFL key — so the spam threat model that motivated a
hard bound does not apply to the request path. A fixed 3/day also blocks the iterative
live quality/method tuning loop (0018), where many real generations must be fired to
eyeball likeness and realism. Proactive selfies are persona-initiated (the LLM-judgment
case story 13 exists to guard), so that cap stays hard.

## Consequences

- `LUVIA_SELFIE_REQUEST_LIMIT` is a real spend lever on a live API key. Set it loose only
  on a trusted single-owner box; a shared/multi-learner deployment must set a finite bound.
- This deliberately deviates from PRD 0003 story 13's "hard-bound" language for the request
  path. It is not a bug — do not re-hardcode `REQUEST_LIMIT` back to a fixed 3.
- Enforcement architecture is unchanged: the plugin still computes and enforces the cap
  from `selfie_log` history; only the request ceiling's value is now tunable.
