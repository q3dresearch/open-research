-- observatory.db schema
-- Source of truth for table structure.
-- Additive migrations for existing DBs are handled by lib/db._migrate().

CREATE TABLE IF NOT EXISTS portals (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    name TEXT,
    api_type TEXT DEFAULT 'ckan',
    last_crawled_at TEXT,
    total_datasets INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    portal_id TEXT NOT NULL REFERENCES portals(id),
    resource_url TEXT,
    title TEXT,
    description TEXT,
    schema_shape TEXT,          -- JSON: [{name, type, description}, ...]
    format TEXT,                -- csv, json, xlsx
    row_count INTEGER,
    dataset_archetype TEXT DEFAULT 'unknown',
        -- transactional | panel | time_series | aggregate_pivot |
        -- aggregate_summary | cross_section | reference | geospatial | unknown
        -- Set authoritatively by EDA (phase 10) from full profile.
    research_mode TEXT DEFAULT 'predictive',
        -- predictive | descriptive | diagnostic | prescriptive
        -- Derived from dataset_archetype + EDA signals. Drives pipeline routing.
    update_frequency TEXT,      -- daily, weekly, monthly, irregular, unknown
    max_action_code TEXT DEFAULT '00',   -- highest completed phase code
    cron_actions TEXT DEFAULT '[]',      -- JSON array of action names
    rejected INTEGER DEFAULT 0,
    rejected_at TEXT,           -- action name where rejection was recorded (e.g. 'vet', 'eda')
    reject_reason TEXT,
    last_run_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    action TEXT NOT NULL,       -- semantic name: vet, eda, clean, engineer, cluster, select, report
    action_code TEXT NOT NULL,  -- sortable code: 00, 10, 15, 20, 25, 30, 50
    agent TEXT,
    status TEXT DEFAULT 'running',
    started_at TEXT DEFAULT (datetime('now')),
    finished_at TEXT,
    prompt_template TEXT,
    llm_response TEXT,          -- full JSON from LLM (verdict + all fields)
    verdict TEXT,
    verdict_reason TEXT,
    artifact_paths TEXT         -- JSON array of relative artifact file paths
);

CREATE TABLE IF NOT EXISTS proposed_joins (
    id TEXT PRIMARY KEY,
    source_dataset_ids TEXT NOT NULL,  -- JSON array
    join_keys TEXT,                    -- JSON array
    proposed_by TEXT,                  -- 'ai' or 'human'
    rationale TEXT,
    status TEXT DEFAULT 'proposed',    -- proposed, approved, rejected
    reviewed_at TEXT,
    reviewer_notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS synthetic_tables (
    id TEXT PRIMARY KEY,
    join_id TEXT REFERENCES proposed_joins(id),
    source_dataset_ids TEXT NOT NULL,
    transformation_process TEXT,
    notebook_path TEXT,
    max_action_code TEXT DEFAULT '00',
    cron_actions TEXT DEFAULT '[]',
    human_notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schema_embeddings (
    dataset_id TEXT PRIMARY KEY REFERENCES datasets(id),
    embedding BLOB,
    text_input TEXT,
    model TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scan_catalog (
    id TEXT PRIMARY KEY,
    portal_id TEXT NOT NULL,
    name TEXT,
    description TEXT,
    format TEXT,           -- CSV | GEOJSON | KML | SHP | XLSX | ...
    size_bytes INTEGER,
    column_count INTEGER,
    status TEXT DEFAULT 'pending',  -- pending | vetted | skipped
    skip_reason TEXT,
    discovered_at TEXT DEFAULT (datetime('now')),
    vetted_at TEXT
);

CREATE TABLE IF NOT EXISTS scan_progress (
    portal_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    scanned_at TEXT DEFAULT (datetime('now')),
    datasets_found INTEGER DEFAULT 0,
    PRIMARY KEY (portal_id, page)
);
