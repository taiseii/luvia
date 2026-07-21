# Selfies via BFL direct + a fixed reference library, not FAL and not a growing set

Sophia can send fictional selfies of herself (PRD 0003). Two coupled decisions shape how,
and both cut against the obvious path.

**Image backend: Black Forest Labs (BFL) direct, not Hermes's native `image_generate`.** The
box already ships an `image_generation_tool` wired to FAL.ai, and reusing it would have been
one line of persona instruction. We don't. It requires a `FAL_KEY` the box does not have and
we don't control provisioning for; the key we *do* have (`FLUX_API`) is a BFL key (`bfl_…`),
incompatible with the FAL routing. So Luvia calls the BFL FLUX.2 pro API directly from a new
plugin tool (`luvia_selfie`), behind a thin one-method generate-image interface, and delivers
the result through the existing `send_message` tool.

**Reference strategy: a fixed, hand-curated library, never auto-grown.** Every selfie is a
single edit-hop off one of five curated reference images of Sophia (a canonical portrait plus
four poses), fed to the API inline as base64. The persona picks which reference to edit; there
is no code-side scene matching. Crucially, generated selfies are *never* fed back into the
library as new references.

Why: identity consistency is the whole point of a selfie — it has to look like the same
person every time, or the illusion the persona depends on shatters. Editing an original keeps
every shot one hop from a real reference. Auto-growing the library (feeding generations back
in) would compound drift — an edit of an edit of an edit slowly stops being Sophia — so the
set stays fixed even though that caps pose variety. BFL-direct keeps us on the key we actually
hold and behind a swappable interface, rather than blocking on FAL infra we'd have to beg for.

Trade-offs accepted: (1) we own a second image vendor's client and its moderation semantics
(`safety_tolerance`) instead of riding the platform's; a future move to FAL/native is a
one-file change but not free. (2) A fixed five-image library means finite pose variety —
scenes will eventually feel samey, and the only remedy is hand-curating more references, never
letting the system self-expand.

Consequences worth recording: the reference library and its `manifest.json` live on the box
only, never the repo (Sophia's likeness must not land on public GitHub — `assets/sophie/` is
gitignored); the `FLUX_API` key is BFL-shaped and any code that assumes FAL will silently
mis-route; and the no-nudity content ceiling is enforced twice (tool-side sanitizer before the
call, BFL `safety_tolerance` at the call) precisely because we're the ones holding the vendor
relationship now. Per ADR-0001, all of this is plugin capability — the persona only decides
*when* to send a selfie, never how one is made.
