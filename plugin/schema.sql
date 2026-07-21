-- Luvia schema, verbatim from luvia-spec.md (modulo IF NOT EXISTS so the
-- plugin can apply it idempotently on every call).
-- Single source of truth, lives on the Hermes server. Multi-user-ready from day one.

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  telegram_user_id TEXT UNIQUE,
  timezone TEXT NOT NULL DEFAULT 'Europe/Amsterdam',
  reference_lang TEXT NOT NULL DEFAULT 'en',
  metadata_json TEXT,              -- interests, contexts, level priors per language
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS languages (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  script TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_items (
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

CREATE TABLE IF NOT EXISTS item_tags (
  item_id INTEGER NOT NULL REFERENCES content_items(id),
  tag TEXT NOT NULL,
  PRIMARY KEY (item_id, tag)
);

CREATE TABLE IF NOT EXISTS learner_items (
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

CREATE TABLE IF NOT EXISTS articles (   -- Phase 2 feature; table ships in Phase 1 schema
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

CREATE TABLE IF NOT EXISTS sessions (
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

CREATE TABLE IF NOT EXISTS session_events (
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

CREATE TABLE IF NOT EXISTS method_profiles (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  version INTEGER NOT NULL,
  config_yaml TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Experiment tooling is Phase 3; tables ship now because schema is cheap and history isn't.
CREATE TABLE IF NOT EXISTS experiments (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  hypothesis TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS experiment_arms (
  id INTEGER PRIMARY KEY,
  experiment_id INTEGER NOT NULL REFERENCES experiments(id),
  method_profile_id TEXT NOT NULL REFERENCES method_profiles(id),
  weight REAL NOT NULL DEFAULT 1
);

-- One row per generated selfie, keyed by learner. Quota windows (proactive
-- <= 1 / rolling 72h, on-request <= 3 / rolling 24h) are computed purely from
-- this history over trailing windows, never from chat context.
CREATE TABLE IF NOT EXISTS selfie_log (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  trigger_source TEXT NOT NULL CHECK (trigger_source IN ('proactive', 'request')),
  created_at TEXT NOT NULL             -- UTC ISO 8601 timestamp
);

-- Serves the hot quota read: count a learner's selfies of one source over a
-- trailing window.
CREATE INDEX IF NOT EXISTS idx_selfie_log_quota
  ON selfie_log (user_id, trigger_source, created_at);
