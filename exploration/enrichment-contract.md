# Seed Enrichment Contract (v2 — deterministic-first)

Purpose: define the seed enrichment stage precisely. v1 assumed an LLM enriched every item;
a coverage benchmark (`kaikki_coverage.py`, run 2026-07-20) showed that is overkill — the
enrichment is almost entirely deterministic lookup. A model handles only two residual jobs.

## Deterministic sources (benchmarked)

| Source | Provides | Measured coverage on top-3000 draft |
|---|---|---|
| kaikki.org Dutch JSONL (parsed Wiktionary, 247 MB) | lemma existence, POS, de/het gender, EN glosses, register labels, inflection tables | 87.4% direct lemma hit, all with EN gloss; de/het for 83% of nouns with a crude parser (>95% expected with full gender parsing) |
| Tatoeba (CC-BY Dutch–English pairs) | example sentences per form | 94.3% of top-3000 have ≥1 EN-linked Dutch sentence; 93.2% have one ≤12 words (`tatoeba_bench.py`, 148K linked sentences, run 2026-07-20) |

Key finding: **lexicon membership is the keep/drop filter.** The 374 misses were almost
entirely proper nouns and English contamination (harold, vegas, chicago, yeah, mr) — the
junk drops itself. Known fixables: accent normalization (eén), case-insensitive indexing
(Brits was skipped by an islower() filter).

## Pipeline stages

1. Frequency parse → simplemma lemmatize → aggregate (validated, `bench_seed2.py`).
2. **kaikki join**: keep only lemmas present in the lexicon (drops names/junk); attach POS,
   de/het article, all EN glosses, register labels, inflected forms.
3. **Tatoeba join**: shortest natural sentence containing the lemma or an inflected form
   (via the kaikki inflection tables). Measured misses overlap heavily with the kaikki
   junk-drop (names: tommy, ryan, bobby), so the true example-generation residual after
   stage 2 is ~100–200 items.
4. **Model pass (residual only)**:
   - Sense selection: pick the frequency-dominant EN gloss when kaikki lists several
     (first-sense heuristic default; model arbitrates only genuinely ambiguous entries).
   - Example generation: only where Tatoeba has no hit or only stiff/formal sentences —
     output must be informal spoken register (spreektaal), ≤ 12 words.
   - Miss rescue: the handful of real Dutch lemmas absent from kaikki after normalization.
5. Human spot-check on a 150-item sample (ranks 1–50, 995–1045, 2950–3000).

## Model requirement (revised)

Workload is a few hundred items, one-off, run as a **build-time batch via OpenRouter**
(direct API call from the pipeline script — not routed through the Hermes agent at
runtime). At this volume (~100–200K tokens total) cost is cents even on frontier models,
so pick on quality, not price.

Selection protocol: run 2–3 candidates on a ~40-item slice of the residual set, eyeball
Dutch example naturalness (spreektaal, not textbook) and gloss choice, pick one, run the
full batch. No formal gold-set benchmark needed anymore — the hard deterministic fields
are out of the model's hands.

**Model decision (2026-07-20): `google/gemini-3.5-flash` via OpenRouter.** Eyeball run
(`residual_eyeball.py`, 40 items): 40/40 valid JSON, examples genuinely spreektaal
("relaxte vent", "chillen met de boys", "m'n vinger"), gloss choice sensible (zender →
"TV or radio channel", angel → "sting"). Cost $0.31 for 41K tokens — completion-heavy
(thinking tokens), still negligible.

Two findings from the run:

1. **True residual is ~42 items, not 100–200** — Tatoeba misses overlap with kaikki
   junk-drop more than estimated.
2. **Lexicon membership leaks proper nouns and English.** Lowercase given names (annie,
   abby, rebecca, jacob, hank, hector), English contamination (my, love, boy, it), and
   frequency/sense mismatches (kim glossed "horizon" but subtitle frequency is the name;
   bo glossed as Flemish "sandwich") all have kaikki entries, so they survive the join.
   ~⅓ of the residual sample is junk. Fixes: exclude kaikki entries whose only POS is
   `name`, and let the residual model pass emit a drop flag — its `notes` field already
   caught wangeloven (archaic), isogeen (technical), my/love (obsolete spellings).

## Model output contract (residual pass)

```json
{
  "lemma": "zitten",
  "chosen_gloss": "to sit",
  "example_nl": "blijf je nog even zitten?",
  "example_en": "are you staying seated a bit longer?",
  "keep": true,
  "notes": ""
}
```

## Superseded (v1, for the record)

v1 asked a model for: lemma correction, POS, de/het, translation, keep/drop, register,
examples — with a 150-item gold set and a ≥95% article-accuracy bar, and a shortlist of
12–27B local models. The kaikki benchmark made all fields except sense choice and example
generation lookups. Traps that remain true from the bench runs:

- `simplemma.is_known` must NOT be used as a junk filter (rejects van, u, jullie, omdat).
- simplemma noun/verb ambiguity ("eikel" → "eikelen") — resolved by preferring the kaikki
  entry when the simplemma lemma is absent from the lexicon but the raw form is present.
- Subtitle register includes vulgar items — keep, tag via kaikki labels
  (informal/vulgar/slang).
