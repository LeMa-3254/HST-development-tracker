CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_name TEXT NOT NULL,
  tier TEXT NOT NULL,
  authors TEXT NOT NULL DEFAULT '[]',
  published_date TEXT,
  fetched_date TEXT NOT NULL,
  abstract TEXT,
  doi TEXT,
  embedding TEXT,
  relevance_score REAL,
  quality_score REAL,
  score_reason TEXT,
  theme TEXT,
  summary TEXT,
  why_it_matters TEXT,
  digest_date TEXT,
  status TEXT NOT NULL,
  dup_of TEXT
);

CREATE TABLE IF NOT EXISTS weekly_summaries (
  week_start TEXT PRIMARY KEY,
  week_end TEXT NOT NULL,
  synthesis_md TEXT NOT NULL,
  item_ids TEXT NOT NULL,
  generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  counts_json TEXT NOT NULL,
  errors_json TEXT NOT NULL DEFAULT '[]',
  token_usage_json TEXT NOT NULL DEFAULT '{}'
);

-- Three weekly web-search sections, all rendered as site pages. Each payload_json holds the
-- model's JSON object for that week; all three share the same shape and the generic
-- _upsert_section / _latest_section helpers in store/db.py.

-- Materials (tubing family -> base polymer + crosslinking route -> property targets -> open
-- challenge). payload_json holds {"materials": [...]}.
CREATE TABLE IF NOT EXISTS material_requirements (
  week_start TEXT PRIMARY KEY,
  week_end TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  generated_at TEXT NOT NULL
);

-- Notable Products (real launches from the tubing vendors). payload_json holds {"products": [...]}.
CREATE TABLE IF NOT EXISTS notable_products (
  week_start TEXT PRIMARY KEY,
  week_end TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  generated_at TEXT NOT NULL
);

-- Regulatory Watch (UL/MIL/IEC/SAE/ISO/EPA/ECHA/FDA activity + its impact on a tubing
-- manufacturer). payload_json holds {"regulations": [...]}.
CREATE TABLE IF NOT EXISTS regulatory_watch (
  week_start TEXT PRIMARY KEY,
  week_end TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  generated_at TEXT NOT NULL
);

