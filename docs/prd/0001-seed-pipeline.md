---
title: Luvia seed pipeline
status: ready-for-agent
labels: [ready-for-agent]
---

# PRD 0001 — Seed Pipeline

## Problem Statement

The learner wants to polish Dutch vocabulary toward comfortable everyday conversation
(~3,000 highest-frequency lemmas plus phrases), but Luvia's database is empty. Hand-curating
3,000 enriched vocabulary items (article, translation, register, example sentence) is weeks
of manual work, and naive LLM enrichment of every item was benchmarked and rejected as
overkill. Without seeded content there is nothing to review, nothing for ambient practice to
weave in, and no learning can start.

## Solution

A one-command, build-time pipeline that turns public data into a fully enriched Dutch seed
set: frequency list → lemma aggregation → lexicon join (POS, de/het article, translations,
register, junk-drop) → example-sentence join → a small LLM residual batch via OpenRouter →
loaded into the Luvia SQLite database as content items. Every stage was empirically
validated in the exploration benchmarks; the pipeline productionizes those results and is
rerunnable and resumable.

## User Stories

1. As a learner, I want the top ~3,000 Dutch lemmas seeded with English translations, so that my review queue reflects the vocabulary band needed for casual conversation.
2. As a learner, I want every noun stored with its de/het article, so that I never learn a noun without its gender.
3. As a learner, I want verbs stored as infinitives and separable verbs as single items, so that vocabulary items match dictionary form.
4. As a learner, I want inflected forms folded into their lemma rather than appearing as separate items, so that I don't review "ging" and "gaan" as two cards.
5. As a learner, I want proper nouns and English contamination excluded, so that I never get "bobby" or "yeah" as a Dutch vocabulary item.
6. As a learner, I want each item to carry one natural, short example sentence, so that I see the word used in context.
7. As a learner, I want example sentences in informal spoken register where possible, so that practice matches how my mates actually talk.
8. As a learner, I want vulgar/slang items kept and tagged rather than censored, so that I understand the register my friends use.
9. As a learner, I want each item to carry the frequency-dominant meaning rather than an obscure sense, so that I learn "zitten" as "to sit" first.
10. As a learner, I want items tagged with register and frequency rank, so that the picker can prioritize and filter content sensibly.
11. As a learner, I want the seed load to be idempotent, so that rerunning the pipeline never duplicates items or wipes my learning state.
12. As a maintainer, I want the pipeline runnable as a single command with clear stage boundaries, so that I can rerun any stage after fixing data issues.
13. As a maintainer, I want the LLM residual batch to run via OpenRouter at build time, so that enrichment never depends on the Hermes runtime.
14. As a maintainer, I want the residual batch resumable and cached, so that a failed run doesn't re-spend API calls on completed items.
15. As a maintainer, I want a pipeline report (counts per stage: kept, dropped, joined, residual), so that I can verify each run against the benchmarked expectations (~87% lexicon hit, ~94% example coverage, ~100–200 residual items).
16. As a maintainer, I want dropped items written to a reviewable reject file with drop reasons, so that false drops can be rescued.
17. As a maintainer, I want a human spot-check sample (ranks 1–50, 995–1045, 2950–3000) emitted after each full run, so that quality is verified before the seed reaches the learner.
18. As a maintainer, I want the pipeline to support loading a phrase CSV into the same content pool, so that starter phrases ship the same way lemmas do once onboarding captures the learner's contexts.
19. As a maintainer, I want source attributions recorded per item, so that CC-BY / CC BY-SA obligations are dischargeable if the repo ever goes public.

## Implementation Decisions

- Deterministic-first architecture (per exploration contract v2): the LLM touches only
  sense selection and example generation for items the deterministic joins can't cover
  (~5% of items). All other fields come from lookups.
- Stage order: frequency parse → simplemma lemmatization → frequency aggregation → kaikki
  (parsed Wiktionary) join → Tatoeba join → OpenRouter residual batch → SQLite load.
- Junk filtering is lexicon membership: a lemma absent from the kaikki lexicon (after
  accent normalization and case-insensitive indexing) is dropped with reason. The
  `simplemma.is_known` function must never be used as a filter (verified to reject core
  function words). Membership alone leaks lowercase given names and English contamination
  that have Wiktionary entries (annie, my, love, boy — verified in eyeball run): also drop
  entries whose only kaikki POS is `name`, and honor the residual pass's drop flag.
- Mis-lemmatization resolution rule: when the simplemma output is absent from the lexicon
  but the raw form is present as a lexicon headword, the lexicon headword wins.
- Vocabulary unit is the lemma per the domain glossary: nouns get their article in the
  surface form ("het huis"), verbs are infinitives, separable verbs are one item flagged in
  metadata, inflected forms never become items.
- Example selection: shortest natural Tatoeba sentence (≤12 words preferred) containing the
  lemma or any inflected form from the kaikki inflection tables, with its English
  translation.
- Residual LLM batch: OpenRouter with `google/gemini-3.5-flash` (validated by 40-item
  eyeball test 2026-07-20: natural spreektaal, sensible gloss choice, $0.31); structured
  JSON output including a drop flag; true residual measured at ~42 items.
- Output target: the content-items table of the Luvia schema (defined in PRD 0002), with
  register tags, frequency rank, source attribution, and item type `lemma` (phrases:
  `phrase`).
- Idempotency key: (language, item type, surface); reruns upsert enrichment fields and
  never touch learner-state tables.
- SUBTLEX-NL may be used locally as a ranking cross-check but is never committed or
  redistributed.
- Python tooling via uv; any new dependency gets a one-line audit before install.

## Testing Decisions

- Tests exercise external behavior only: given fixture inputs, assert the final loaded rows
  and the pipeline report counts — not intermediate data structures.
- Primary seam: end-to-end CLI run against small fixtures (frequency-list slice, kaikki
  slice, Tatoeba slice, recorded OpenRouter responses) into a temp SQLite database.
- OpenRouter is injected/mocked at the client boundary; no live API calls in tests.
- Stage-level regression tests only for empirically discovered traps: the is_known
  rejection, proper-noun drop, eikel→eikelen lexicon-wins rule, accent/case normalization.
- Prior art: the three exploration benchmark scripts define the expected stage semantics
  and realistic data shapes for fixtures.

## Out of Scope

- The plugin runtime, tools, scheduler, and skill overlay (PRD 0002 and later).
- Generating the ~200 starter phrases (needs learner contexts captured at onboarding;
  pipeline only supports loading them).
- Articles/RSS ingestion, additional languages, pronunciation data.
- Any Hermes-server deployment concerns (backup role change lives with deployment work).

## Further Notes

Benchmarked coverage figures the pipeline report should be validated against: 87.4% direct
kaikki lemma hit with EN gloss; de/het derivable ≥95% with full gender-template parsing;
94.3% Tatoeba example coverage (93.2% with a ≤12-word sentence); expected residual batch
~100–200 items. Wiktionary-derived data is CC BY-SA — attribution required if the seed data
is ever published.
