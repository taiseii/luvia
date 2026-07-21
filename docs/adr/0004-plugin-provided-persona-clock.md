# Persona clock provided by the plugin (`luvia_now`), not the host

The persona routine (CONTEXT.md) infers the carrier persona's current activity from the learner's local time-of-day. The runtime does not supply that time-of-day: Hermes injects only the current **date** into the system prompt — deliberately, minute precision would invalidate the prefix-cache KV on every rebuild — and its timezone defaults to the server's (UTC). Recalled memory carries the learner's IANA timezone but is static text; it cannot compute "now." So the persona has no hour in context and guesses the block (it wished the learner "goedemorgen" at 01:00 local).

The obvious fix — have Hermes inject the time-of-day, or add a host time-tool — is closed to us on two counts. ADR-0001 and the glossary hold that Luvia extends Hermes but never modifies it, and passive per-turn context injection is only exposed to `kind: memory-provider` plugins (via `system_prompt_block`), not to a `kind: standalone` tool plugin like Luvia. The hour therefore has to be **computed fresh**, which means a tool call.

**Decision.** Luvia owns the persona clock. A dedicated tool, `luvia_now`, returns the current local time and weekday computed from the learner's stored `users.timezone`; the **skill** maps that time to a routine block (the plugin never holds the block table — persona flavor stays in the skill, per ADR-0001). Every other luvia tool result is additionally stamped with `local_time` as defense-in-depth, so any tool call refreshes the persona's clock even if it skips `luvia_now`.

## Considered options

- **Piggyback the clock on `luvia_plan_today`.** Rejected: `plan_today` runs once per day (first exchange), so its time-of-day is stale by evening — the wrong cadence for a per-wake clock.
- **Set `HERMES_TIMEZONE` and rely on the injected timestamp.** Insufficient alone: the injection is date-only by design; a correct timezone still yields no hour. (Still worth setting so the host's date rolls at the learner's midnight, but it does not solve the persona clock.)
- **Become / register a memory-provider to gain `system_prompt_block`.** Rejected: a large change to the plugin's kind and lifecycle to buy passive injection Luvia does not otherwise need.

## Consequences

- The clock is only as reliable as the persona choosing to call a tool. The per-return `local_time` stamp and a hardened wake instruction ("first action each wake: `luvia_now`") mitigate this, but a turn that calls no luvia tool still has no fresh hour — an accepted limit of a tools-only plugin surface.
- `users.timezone` becomes load-bearing for persona realism, not just record-keeping. A missing/invalid timezone must degrade safely (the skill asks the learner once, in character, and stores it).
