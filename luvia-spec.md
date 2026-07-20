# Luvia — Language Learning Extension for Hermes

## Overview

Luvia is a Hermes Agent extension for language learning: a Python plugin (SQLite state, SRS
engine, content selection) plus a persona-agnostic overlay skill that turns the learner's
existing companion persona into a bilingual practice partner. First deployment: Dutch for a
single A2 learner whose goal is informal communication with Dutch-speaking friends.

The core design goal is ambient learning — practice woven into natural conversation at
randomized moments through the day — backed by a rigorous SRS engine underneath. There is no
teacher persona and no standalone app. See `CONTEXT.md` for canonical terminology and
`docs/adr/0001-ambient-first-persona-overlay.md` for the central product decision.

## Goals

- Ambient practice as the primary mode: the carrier persona (sophia first) weaves due vocab,
  new items, and Dutch conversation into normal chat, randomized between 10:00 and 24:00
  (Europe/Amsterdam), also invocable on demand ("hey sophia").
- Bilingual code-switching: Dutch at the learner's level, English for explanations and
  whenever comprehension breaks.
- Guaranteed daily exposure to new words and phrases, governed by an adaptive pacing band.
- All learner data in SQLite on the Hermes server; the plugin reconstructs state from the
  database at runtime (cron sessions carry no chat memory).
- Methodology as configuration (method profiles), not hardcoded product logic.
- Scheduler behind a swappable interface so SM-2 can be replaced by FSRS without data loss.

## Non-goals

- A standalone mobile/web UI.
- Modifying Hermes core — plugins, skills, and Chronos cron cover everything needed.
- Depending on any specific persona: all persona coupling lives in skill instructions.
- A complete course for every language in v1. Dutch first; schema is language-agnostic.

## Verified Hermes facts (from NousResearch/Hermes-Agent source)

- Plugins are Python packages under `plugins/<name>/` with a `plugin.yaml` manifest
  (name, version, kind, tool list), `tools.py`, and optional support modules. Tool names are
  snake_case with plugin prefix (`spotify_playback`) — Luvia tools are `luvia_*`.
- Skills are `SKILL.md` packages (agentskills.io standard), invoked as `/<skill-name>`,
  composable with other active skills.
- Chronos managed cron exists (`docs/chronos-managed-cron-contract.md`,
  `plugins/cron_providers/`) with delivery to platforms including Telegram.
- The Telegram adapter supports inline keyboards; the agent-invocable **clarify tool**
  (`send_clarify`) renders one button per choice plus an "Other (type answer)" fallback —
  this is the grading-button surface for review mode.
- The gateway auto-transcribes incoming Telegram voice notes (`tools/transcription_tools.py`;
  local faster-whisper default, Groq `whisper-large-v3-turbo` recommended for Dutch) and can
  send TTS voice notes back (`tts_tool.py`). Voice-based practice is therefore cheap
  (Phase 1.5), not a Phase 3 moonshot. Caveat: Whisper silently cleans up grammar, so
  transcripts are valid for communication grading, not pronunciation scoring.
- Hermes runs on a remote server; the Luvia SQLite database lives there too. Inspection is
  via Hermes or SSH, and backups must be explicit (see Risks).

## Product model

| Layer | Responsibility |
|---|---|
| Data | SQLite: users, content items, learner state, sessions, events, method profiles |
| Mechanisms | Primitive operations: exposure, retrieval, recognition, production, imitation, transformation, correction, reflection, scheduling |
| Method profiles | Named methodology bundles expressed as YAML config |
| Interaction | Ambient practice (primary), review mode (daily SRS workhorse), conversation mode; delivered through the carrier persona on Telegram |

One learner-state model serves all methods; named methodologies are combinations of the same
mechanisms, not distinct systems.

## Interaction modes

### Ambient practice (primary)

Jittered cron pings (see Scheduling) wake the persona with a small batch from
`luvia_pick_items`. The persona decides in the moment whether to weave practice in or just
chat. Practice looks like conversation: "hoe zeg je 'deadline' ook alweer in het
nederlands?" — the learner's reply is graded implicitly and logged via `luvia_record_result`.
No visible rubric, no scores shown, no teacher register. Comprehension failures trigger an
instant English rescue and are logged as adaptation signals.

### Review mode (explicit, daily)

Learner-invoked flashcard mode carrying the bulk SRS load. Prompt → learner answers (typed,
or thinks) → reveal → grading buttons via the clarify tool: **Again / Good / Easy**, plus
**Already knew** on first encounter (fast-track). Button taps make `latency_ms` meaningful;
typed-chat latency is treated as noise. 5–10 minutes daily; the pacing band assumes this
happens.

### Conversation mode

Free informal Dutch dialogue with selective, delayed correction. Register is spreektaal —
"hoi, alles goed?", never "hoe maakt u het". Phase 1.5 adds voice: learner sends voice notes
(graded from transcript), persona sends TTS voice notes for listening practice.

The spec's original state machine
(`plan → warmup → review → new_input → guided_output → correction → reflection → schedule → summary`)
applies only inside review and conversation modes. Ambient bursts are free-form.

## Learner model and pacing

### Intake policy

- Seed items all enter as `status='new'`; no placement test. The SRS sorts knowns from
  unknowns via the first-encounter **fast-track**: "Already knew" jumps an item straight to
  a ~30-day interval with an ease bump. The learner's existing A2 vocabulary (~1,000–1,500
  lemmas) sweeps through in the first weeks; sweeps do not consume the pacing band.
- **Pacing band**: 35–70 genuinely-new items per week, starting at 50. Ratcheted weekly on
  a trailing two-week window: recall ≥85% and daily completion → +5–10/week; recall <70% or
  3+ skipped days → down. The binding constraint is the review-load ceiling (~100
  touches/day), not the band; sustained top performance triggers a proposal to raise the
  band rather than silent grinding.
- New-item intake is never starved by review backlog: daily reviews are capped, overflow
  spills forward. Daily new exposure is guaranteed (band floor > 0).
- Target: ~3,000 highest-frequency lemmas plus phrases — the research-backed band for
  comfortable everyday conversation (top 3,000 word families ≈ 95% coverage of casual
  speech; B1 vocabulary). At the recommended pace this lands 6–8 months out.

### Adaptation layer

`language_mix` and difficulty are driven by observed comprehension, not CEFR labels (A2 is
a starting prior only). Every ambient exchange logs comprehension signals (reply quality,
"wat betekent dat?" requests, English rescues). Dutch ratio, sentence complexity, and vocab
band ratchet up as comprehension holds, back off when it breaks.

Inputs: recall rate, response latency (buttons only), confidension self-ratings, repeated
error types, completion, comprehension-break rate.
Outputs: review/new balance, phrases vs words, input vs output, correction timing,
language_mix, temporary profile switch.

## Scheduler

SM-2 variant in Phase 1, behind a swappable interface:

```python
def schedule(item_state: SchedulerState, grade: Grade, now: datetime) -> tuple[SchedulerState, datetime]: ...
```

- Grades: `again / good / easy / already_knew` (last one first-encounter only).
- Algorithm parameters live in `learner_items.scheduler_state_json` (SM-2: ease, interval;
  FSRS later: stability, difficulty) — no algorithm-specific columns in the schema.
- Every review is logged in full in `session_events` (grade, timestamp, latency); that is
  exactly the history the FSRS optimizer needs, so the swap is: implement interface, run one
  migration that re-fits state from history. Zero data loss.

## Content

### Content items

One pool (`content_items`) for all methods. Item types: lemma, phrase, dialogue turn,
grammar pattern, task, article, quiz item, listening snippet.

Vocabulary unit is the **lemma**: nouns stored with article in `surface` ("het huis"),
verbs as infinitives, separable verbs one item flagged in `metadata_json`, inflected forms
never separate items (they appear in example sentences). There is no separate phrases
table — phrases are `content_items` rows with `item_type='phrase'`, so they get full SRS
state like everything else.

### Seed pipeline (validated in `exploration/`)

1. Source: hermitdave/FrequencyWords Dutch list (OpenSubtitles 2018, CC-BY) — spoken
   register, matching the learner's goal. SUBTLEX-NL used privately as a ranking
   cross-check, never committed.
2. Deterministic stages (benchmarked, `exploration/nl_lemmas_top3000_draft.csv`): parse →
   `simplemma` lemmatize → frequency-aggregate. Top ~4,500 raw forms yield ~3,000 lemmas
   (23% reduction). Known traps, found empirically: `simplemma.is_known` must NOT be used
   as a junk filter (rejects core function words); proper nouns survive frequency filtering;
   noun/verb lemma ambiguity ("eikel" → "eikelen").
3. Enrichment is deterministic-first (`exploration/enrichment-contract.md` v2, benchmarked
   with `exploration/kaikki_coverage.py`): a kaikki.org parsed-Wiktionary join supplies
   POS, de/het article, EN glosses, register labels, and — via lexicon membership — the
   proper-noun/junk drop filter (87.4% direct coverage measured on the draft list); a
   Tatoeba join supplies example sentences. An LLM handles only the residuals —
   frequency-dominant sense selection and spreektaal example generation where Tatoeba has
   no natural hit — run as a build-time batch via OpenRouter (model picked by a small
   quality eyeball-test; volume is ~100–200K tokens so cost is negligible). Human
   spot-check on a 150-item sample closes the pipeline.
4. Phrase seed: ~200 starter phrases generated from the learner's actual contexts —
   captured by the persona during onboarding (interests, region, work/social settings) —
   not from a phrasebook. Vulgar/slang subtitle vocabulary is kept and tagged
   `register: vulgar`; mates-register Dutch is the point.

## Supported methodologies

Phase 1 ships two profiles; the rest are config away.

| Profile | Characteristics | Key mechanisms | Phase |
|---|---|---|---|
| `frequency_srs` | High-frequency lemmas/phrases with spaced review | retrieval, recognition, scheduling | 1 |
| `communicative_hybrid` | Informal functional communication, selective correction | production, correction, exposure | 1 |
| `comprehensible_input` | Input slightly above level | exposure, light reflection | 2 |
| `news_clil` | News/topical content | exposure, production, reflection | 2 |
| `task_based` | Practical language tasks | production, exposure, reflection | 2 |
| `audio_drill` | Automaticity via repetition | imitation, transformation, correction | 2–3 |
| `adaptive_mix` | Mechanism blend from performance history | all | 2 |

### Method profile schema

```yaml
id: communicative_hybrid
label: Communicative Hybrid
version: 1
register: informal          # spreektaal; formal register only on request
language_mix: adaptive      # driven by comprehension signals, CEFR prior A2
modality_weights: { reading: 0.20, listening: 0.20, speaking: 0.40, writing: 0.20 }
mechanism_weights: { exposure: 0.20, retrieval: 0.20, production: 0.35, correction: 0.15, reflection: 0.10 }
content_weights: { lemmas: 0.20, phrases: 0.35, dialogues: 0.25, tasks: 0.20 }
correction_policy: delayed_selective
new_item_ratio: 0.15
review_ratio: 0.35
free_production_ratio: 0.25
success_metrics: [recall_rate, response_latency, comprehensibility, confidence]
```

## SQLite schema

Single source of truth, lives on the Hermes server. Multi-user-ready from day one.

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  telegram_user_id TEXT UNIQUE,
  timezone TEXT NOT NULL DEFAULT 'Europe/Amsterdam',
  reference_lang TEXT NOT NULL DEFAULT 'en',
  metadata_json TEXT,              -- interests, contexts, level priors per language
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE languages (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  script TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE content_items (
  id INTEGER PRIMARY KEY,
  lang TEXT NOT NULL REFERENCES languages(code),
  item_type TEXT NOT NULL,         -- lemma | phrase | dialogue_turn | grammar_pattern | task | article_ref | quiz | listening
  surface TEXT NOT NULL,           -- nouns include article: "het huis"
  base_form TEXT,
  pos TEXT,
  meaning TEXT,
  translation TEXT,                -- in reference_lang
  pronunciation TEXT,
  register TEXT,                   -- neutral | informal | vulgar | formal
  example TEXT,                    -- informal example sentence
  notes TEXT,
  difficulty REAL DEFAULT 0,
  frequency_rank INTEGER,
  source TEXT,
  metadata_json TEXT,              -- e.g. {"separable": true}
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE item_tags (
  item_id INTEGER NOT NULL REFERENCES content_items(id),
  tag TEXT NOT NULL,
  PRIMARY KEY (item_id, tag)
);

CREATE TABLE learner_items (
  user_id INTEGER NOT NULL REFERENCES users(id),
  item_id INTEGER NOT NULL REFERENCES content_items(id),
  status TEXT NOT NULL DEFAULT 'new',   -- new | learning | review | known | suspended
  due_at TEXT,
  last_seen_at TEXT,
  last_score REAL,
  success_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  scheduler_state_json TEXT,            -- algorithm-owned params (SM-2 now, FSRS later)
  listening_score REAL,
  speaking_score REAL,
  reading_score REAL,
  writing_score REAL,
  notes TEXT,
  PRIMARY KEY (user_id, item_id)
);

CREATE TABLE articles (                 -- Phase 2 feature; table ships in Phase 1 schema
  id INTEGER PRIMARY KEY,
  lang TEXT NOT NULL REFERENCES languages(code),
  title TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  source_name TEXT,
  published_at TEXT,
  fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  summary TEXT,
  simplified_text TEXT,
  difficulty REAL,
  topic TEXT,
  metadata_json TEXT
);

CREATE TABLE sessions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  lang TEXT NOT NULL REFERENCES languages(code),
  mode TEXT NOT NULL,                   -- ambient | review | conversation
  method_profile_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,                        -- ambient: gap-closed (~30 min silence)
  duration_seconds INTEGER,
  summary TEXT,
  self_rating REAL,
  computed_score REAL,
  metadata_json TEXT
);

CREATE TABLE session_events (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES sessions(id),
  event_index INTEGER NOT NULL,
  mechanism TEXT NOT NULL,
  item_id INTEGER REFERENCES content_items(id),
  prompt TEXT,
  learner_response TEXT,
  grade TEXT,                           -- again | good | easy | already_knew (null for non-graded)
  score REAL,
  feedback TEXT,
  latency_ms INTEGER,                   -- meaningful for button taps, noise for typed chat
  comprehension_break INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE method_profiles (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  version INTEGER NOT NULL,
  config_yaml TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Experiment tooling is Phase 3; tables ship now because schema is cheap and history isn't.
CREATE TABLE experiments (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  hypothesis TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE experiment_arms (
  id INTEGER PRIMARY KEY,
  experiment_id INTEGER NOT NULL REFERENCES experiments(id),
  method_profile_id TEXT NOT NULL REFERENCES method_profiles(id),
  weight REAL NOT NULL DEFAULT 1
);
```

Sessions are **gap-based bursts**: contiguous practice exchanges less than ~30 minutes apart
group into one session row; invisible to the learner. "Completion rate" means share of due
items cleared by end of day — not "did you finish a session".

## Tool contract

Snake_case with `luvia_` prefix, per Hermes convention.

| Tool | Purpose | Phase |
|---|---|---|
| `luvia_setup` | Create/update user, capture onboarding context (interests, region) | 1 |
| `luvia_plan_today` | Daily plan: due load, new intake, suggested mode balance | 1 |
| `luvia_pick_items` | Mode-aware selection: review due-batch / ambient micro-batch / new intake | 1 |
| `luvia_record_result` | Log one practice event AND update scheduling in one call | 1 |
| `luvia_score_response` | Deterministic scoring (exact/fuzzy match) before any LLM judgment | 1 |
| `luvia_set_method` | Activate a method profile | 1 |
| `luvia_stats` | Progress metrics, pacing-band state, weekly summary data | 1 |
| `luvia_mix_methods` | Temporary weighted hybrid profile | 2 |
| `luvia_fetch_article` / `luvia_pick_article` | RSS ingestion and level-matched selection | 2 |
| `luvia_experiment_assign` | Method-arm assignment | 3 |

`luvia_record_result` folds the old `run_step` + `schedule_item` pair into one atomic call —
ambient grading must be single-shot or the persona will forget to schedule.

## Skill design

`skills/luvia/SKILL.md` — a persona-agnostic overlay, composable with the active carrier
persona (sophia first). It instructs the persona to:

- Weave practice into its own voice; never switch to teacher register.
- Pull batches via `luvia_pick_items` on cron pings; decide in-context whether to practice
  or just chat; log everything via `luvia_record_result`.
- Code-switch: Dutch at level, English rescue on comprehension break (and log the break).
- Run review mode on request or gentle daily nudge, using clarify buttons for grades.
- Explain grammar in English when asked; keep corrections selective and delayed in
  conversation mode, immediate in review mode.
- During onboarding, capture interests/contexts into `luvia_setup` for phrase seeding and
  content tagging.

Sub-documents: method profile YAMLs, mode prompts (ambient weaving patterns, review flow,
conversation openers), rubrics (comprehension, production).

## Scheduling

- Chronos cron drives ambient pings: an hourly job between 10:00 and 24:00
  (Europe/Amsterdam) that fires probabilistically — the plugin decides fire/skip from
  remaining daily budget, randomness, learner activity, and recent load. This yields
  jittered, natural-feeling touches without relying on Chronos supporting native jitter.
- Learner can start anything anytime ("hey sophia").
- Weekly stats summary (Sunday): recall rate, new lemmas learned, sweep progress,
  review load, comprehension trend, pacing-band position.
- Missed days: items stay due, next day slightly longer, capped — no guilt backlog.
- Cron runs are fresh sessions: the plugin always reconstructs state from SQLite.

## Deployment

Separate repo (this one) — never a fork of Hermes. `deploy.sh` syncs `plugin/` into the
server's `plugins/luvia/` and `skills/luvia/` into its skills directory. The SQLite database
lives on the server under the Hermes data directory.

## Repo layout

```text
luvia/
├── CONTEXT.md                  # canonical domain language
├── docs/adr/                   # decisions
├── exploration/                # seed-pipeline benchmark artifacts (committed)
│   ├── nl_lemmas_top3000_draft.csv
│   └── enrichment-contract.md
├── plugin/
│   ├── __init__.py
│   ├── plugin.yaml
│   ├── tools.py                # luvia_* tool surface
│   ├── store.py                # SQLite access
│   ├── scheduler.py            # Scheduler interface + SM2Scheduler
│   ├── picker.py               # content selection (ambient/review batches)
│   ├── pacing.py               # pacing band + adaptation layer
│   └── scorer.py               # deterministic scoring
├── skills/luvia/
│   ├── SKILL.md
│   ├── methods/*.yaml
│   ├── prompts/*.md
│   └── rubrics/*.yaml
├── seed/
│   ├── pipeline.py             # freq list → lemmas → enrichment → load
│   └── phrases/                # generated starter phrases
├── db/
│   ├── schema.sql
│   └── migrations/
├── deploy.sh
└── tests/
```

## Phases

### Phase 1 — core loop

- Schema + users table; seed pipeline complete (enrichment via learner-selected local model,
  benchmarked per `exploration/enrichment-contract.md`); Dutch top ~3,000 lemmas + ~200
  context phrases.
- SM-2 scheduler behind swappable interface; fast-track; pacing band 35–70/wk start 50.
- Review mode with clarify grading buttons; ambient overlay skill v1 on sophia; jittered
  cron 10:00–24:00; bilingual code-switching; weekly stats summary.
- Profiles: `frequency_srs`, `communicative_hybrid` (informal register).

### Phase 1.5 — voice

- Voice-note production: learner speaks Dutch, grading from auto-transcription
  (Groq `whisper-large-v3-turbo` for Dutch).
- TTS listening exercises: persona sends Dutch voice notes.

### Phase 2 — breadth

- Article ingestion (Dutch RSS: NOS Jeugdjournaal, nu.nl) + `news_clil`,
  `comprehensible_input`, `task_based` profiles; method mixing; full adaptive layer;
  richer conversation scoring; topic specialization from onboarding interests.

### Phase 3 — depth

- Experiment tooling (`luvia_experiment_assign`, time-window comparisons).
- Pronunciation-aware scoring (transcription alone can't do this).
- FSRS swap evaluation (re-fit from `session_events` history).
- More languages; community method packs.

## Risks and constraints

- Whisper transcripts overstate grammatical accuracy (silent cleanup) — never use them for
  accuracy metrics, only communication grading.
- LLM scoring is noisy: deterministic heuristics first (`luvia_score_response`), LLM only
  as fallback, rubric-constrained.
- Ambient throughput is low; if daily review mode lapses, the pacing band must drop —
  the adaptation layer treats skipped review days as a first-class down signal.
- Persona drift: the overlay must not turn the carrier persona into a teacher; register
  rules live in the skill and need periodic review.
- DB on remote server: the Hermes box already runs an hourly systemd backup (sqlite3
  `.backup` snapshot of `state.db`, tar of `$HERMES_HOME`, upload to Hetzner Object Storage,
  hourly x6 / daily x7 retention, integrity check — see hermes repo
  `ansible/roles/backup/`). Gap: a live `luvia.db` in `$HERMES_HOME` would be tar'd as a
  torn-write-prone raw copy. Required change when deploying: extend the backup role to
  snapshot `luvia.db` exactly like `state.db` (`.backup` + exclude live file and WAL/SHM
  sidecars).
- Subtitle-derived seed data needs the enrichment keep/drop pass — proper nouns and
  mis-lemmatizations are present in the draft list (verified empirically).
