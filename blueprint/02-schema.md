# Database Schema
<!-- version: 0.1 | phase: 2 | last-updated: 2026-03-25 -->

## Provider

- **Database:** SQLite3
- **ORM:** Raw SQL via sqlite3 stdlib (wrapped in lib/db.py helpers)
- **Multi-tenant:** No — single operator

## Entity Relationship Diagram

```
portals ──── 1:N ──── datasets ──── 1:N ──── runs
                          │                     │
                          │                     └──── artifacts (paths in runs.artifact_paths)
                          │
                          └──── N:M ──── proposed_joins
                                              │
                                              └──── 1:1 ──── synthetic_tables
                                                                  │
                                                                  └──── 1:N ──── runs (same table, polymorphic)
```

## Tables

### portals

The registry of CKAN portal URLs. Append a row to expand scope.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT | PK | slug: e.g. `data-gov-sg` |
| url | TEXT | UNIQUE, NOT NULL | Base URL: `https://data.gov.sg` |
| name | TEXT | | Human-readable: `Data.gov.sg` |
| api_type | TEXT | DEFAULT 'ckan' | `ckan`, `socrata`, `custom` (future) |
| last_crawled_at | TEXT | | ISO datetime of last scout run |
| total_datasets | INTEGER | DEFAULT 0 | Count of datasets discovered |
| active | BOOLEAN | DEFAULT 1 | Toggle off to stop scouting |
| created_at | TEXT | DEFAULT datetime('now') | |
| updated_at | TEXT | DEFAULT datetime('now') | |

### datasets

**THE GAME STATE TABLE.** Every discovered dataset is a row. `max_level` + `cron_levels` are the score.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT | PK | `{portal_id}:{resource_id}` |
| portal_id | TEXT | FK → portals(id), NOT NULL | |
| resource_url | TEXT | | Direct download or API endpoint |
| title | TEXT | | From CKAN metadata |
| description | TEXT | | From CKAN metadata |
| schema_shape | TEXT | | JSON: `[{name, type, description}, ...]` |
| format | TEXT | | `csv`, `json`, `xlsx` |
| row_count | INTEGER | | From CKAN metadata if available |
| update_frequency | TEXT | | `daily`, `weekly`, `monthly`, `irregular`, `unknown` |
| max_level | INTEGER | DEFAULT 0 | Highest tier completed (0=discovered) |
| cron_levels | TEXT | DEFAULT '[]' | JSON array: which levels are actively cron'd |
| rejected | BOOLEAN | DEFAULT 0 | |
| rejected_at_level | INTEGER | | Which level it failed at |
| reject_reason | TEXT | | LLM's reasoning for rejection |
| human_notes | TEXT | | Operator's metadata, discoveries, steering notes for future levels |
| last_run_at | TEXT | | ISO datetime of most recent run |
| created_at | TEXT | DEFAULT datetime('now') | |
| updated_at | TEXT | DEFAULT datetime('now') | |

**Key queries:**
- `SELECT * FROM datasets WHERE max_level = 0 AND rejected = 0` → level-0 rows needing schema vet
- `SELECT * FROM datasets WHERE max_level >= 1 AND rejected = 0 AND max_level < 2` → ready for lv1 EDA
- `SELECT * FROM datasets WHERE cron_levels != '[]'` → all graduated (producing output)
- `SELECT * FROM datasets WHERE rejected = 1 ORDER BY rejected_at_level` → rejection audit

### runs

Every pipeline execution. The quest log.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT | PK | UUID |
| dataset_id | TEXT | FK → datasets(id), NOT NULL | Or synthetic_table_id for joins |
| entity_type | TEXT | DEFAULT 'dataset' | `dataset` or `synthetic` |
| level | INTEGER | NOT NULL | Which tier was run |
| agent | TEXT | | `scout`, `vetter`, `analyst`, `cartographer`, `publisher` |
| status | TEXT | DEFAULT 'running' | `running`, `passed`, `failed`, `rejected` |
| started_at | TEXT | DEFAULT datetime('now') | |
| finished_at | TEXT | | |
| prompt_template | TEXT | | Which prompt file was used (e.g. `research-00-schema-vet.md`) |
| llm_input | TEXT | | The full prompt sent to LLM (for audit) |
| llm_response | TEXT | | The LLM's full response |
| verdict | TEXT | | `pass`, `fail`, `reject` |
| verdict_reason | TEXT | | LLM's reasoning summary |
| artifact_paths | TEXT | | JSON: list of paths to notebooks, charts, logs |
| metrics | TEXT | | JSON: `{rows_processed, columns, missing_pct, ...}` |
| code_version | TEXT | | Git commit hash at time of run |
| cost_estimate_usd | REAL | | Estimated Claude API cost |
| human_review | TEXT | | Operator's notes after reviewing this run |
| human_verdict_override | TEXT | | If operator overrides: `pass` or `reject` |

### proposed_joins

Cross-dataset join proposals from Cartographer or operator.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT | PK | UUID |
| source_dataset_ids | TEXT | NOT NULL | JSON array of dataset ids |
| join_keys | TEXT | | JSON: `[{left_col, right_col, join_type}, ...]` |
| proposed_by | TEXT | | `ai` or `human` |
| rationale | TEXT | | Why this join is interesting |
| status | TEXT | DEFAULT 'proposed' | `proposed`, `approved`, `rejected` |
| reviewed_at | TEXT | | |
| reviewer_notes | TEXT | | Operator's decision reasoning |
| created_at | TEXT | DEFAULT datetime('now') | |

### synthetic_tables

Approved joins that become new research entities. Enter the same level/cron system.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT | PK | UUID |
| join_id | TEXT | FK → proposed_joins(id) | |
| source_dataset_ids | TEXT | NOT NULL | JSON array |
| transformation_process | TEXT | | Text: how to go from raw → joined |
| notebook_path | TEXT | | Clean notebook for the full join pipeline |
| max_level | INTEGER | DEFAULT 0 | Same level system as datasets |
| cron_levels | TEXT | DEFAULT '[]' | Same cron system |
| human_notes | TEXT | | |
| created_at | TEXT | DEFAULT datetime('now') | |
| updated_at | TEXT | DEFAULT datetime('now') | |

### schema_embeddings

Cached embeddings for similarity search.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| dataset_id | TEXT | PK, FK → datasets(id) | |
| embedding | BLOB | | numpy float32 array, serialized |
| text_input | TEXT | | The text that was embedded (for debugging) |
| model | TEXT | | e.g. `claude-3-haiku-20240307` |
| created_at | TEXT | DEFAULT datetime('now') | |

## Indexes

| Table | Index | Columns | Type | Why |
|---|---|---|---|---|
| datasets | idx_datasets_portal | portal_id | non-unique | Filter by portal |
| datasets | idx_datasets_level | max_level, rejected | composite | Find datasets at each tier |
| datasets | idx_datasets_cron | cron_levels | non-unique | Find graduated datasets |
| runs | idx_runs_dataset | dataset_id | non-unique | All runs for a dataset |
| runs | idx_runs_level | dataset_id, level | composite | Runs for a dataset at a tier |
| runs | idx_runs_status | status | non-unique | Find running/failed runs |
| proposed_joins | idx_joins_status | status | non-unique | Filter pending proposals |

## Seed Data

```sql
-- First portal
INSERT INTO portals (id, url, name, api_type)
VALUES ('data-gov-sg', 'https://data.gov.sg', 'Data.gov.sg', 'ckan');

-- No dataset seeds — Scout agent fills these automatically
```

## Migration Strategy

- Schema defined in `lib/db.py` as a `CREATE TABLE IF NOT EXISTS` block
- For schema changes: add a `migrations/` folder with numbered SQL files
- Each migration is idempotent (IF NOT EXISTS, IF NOT column)
- SQLite doesn't support all ALTER TABLE operations — some changes require table recreation
- Always back up the .db file before running migrations
