# Persona clock via gateway message-timestamp injection, not a plugin tool

The persona routine (CONTEXT.md) infers the carrier persona's current activity from the learner's local time-of-day. The runtime does not put that time-of-day where the persona can see it by default: Hermes injects only the **date** into the system prompt (minute precision would invalidate the prefix-cache KV on every rebuild), and its timezone defaults to the server's (UTC). So the persona had no hour in context and guessed the block — it wished the learner "goedemorgen" at 01:00 local.

**Decision.** Turn on Hermes' own per-message clock rather than building one in the plugin. The gateway has a `message_timestamps` feature (`gateway/message_timestamps.py`), OFF by default, that prefixes every inbound user message the model sees with a timezone-aware `[%a %Y-%m-%d %H:%M:%S %Z]` stamp (e.g. `[Tue 2026-07-22 01:40:53 CEST]`), rendered in the timezone `hermes_time` resolves. We enable it in the box `config.yaml` (`gateway.message_timestamps.enabled: true`) and set the timezone to the learner's (`Europe/Amsterdam`). The **skill** reads that prefix on the latest message as "now" and maps it to the routine block (the plugin never holds the block table — persona flavor stays in the skill, per ADR-0001).

This is passive: the hour is in context on every turn with no tool call, so it does not depend on the persona choosing to act — the property that makes it reliable. It is a config toggle, so it respects "Luvia never modifies Hermes."

## Considered options

- **A plugin-provided `luvia_now` tool** (computing local time from `users.timezone`), backstopped by stamping `local_time` on every luvia return. This was the *first draft of this ADR*, chosen before the gateway feature was found. Rejected once `message_timestamps` surfaced: a tool clock depends on the persona calling it (demonstrably unreliable this project), goes stale between calls, and adds plugin code for something the host already does passively and correctly.
- **Rely on the system-prompt timestamp.** Insufficient: date-only by design; a correct timezone still yields no hour.
- **Modify Hermes to inject time-of-day into the system prompt.** Rejected: violates the never-modify-Hermes boundary, and is unnecessary given the gateway toggle.

## Consequences

- `config.yaml` (box-only, never repo) gains `gateway.message_timestamps.enabled: true` and a `timezone`. This is host provisioning, alongside the other 0018 box config.
- The timezone config becomes load-bearing for persona realism, not just record-keeping. A wrong/absent timezone renders the stamp in UTC and the persona reads the wrong block.
- The skill must be told to read the leading `[...]` stamp as the current time; it is present on every message, so there is no freshness or cadence concern.
- `users.timezone` (captured at onboarding) still records the learner's zone for plugin-side date logic, but the persona's *felt* clock now comes from the gateway stamp, not the plugin.
