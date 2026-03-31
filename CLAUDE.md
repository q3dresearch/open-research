# q3d Open Research — Claude Context

## What this repo is

Autonomous research pipeline that crawls public data portals, vets datasets through graduated tiers using LLM judgment, and produces analysis artifacts.

## Directory structure

```
open-research/
  agents/          ← autonomous scripts (vetter, analyst, cleaner, deep_analyst, clusterer, selector, reporter)
  configs/         ← user-facing files
    ingest.yaml    ← paste dataset URLs here for processing
    portals.yaml   ← portal registry (data.gov.sg, etc.)
    prompts/       ← LLM prompt templates
  data/            ← raw downloaded CSVs (gitignored, never committed)
  lib/             ← shared Python library (db, ckan, eda, llm)
  sql/             ← schema.sql, indexes.sql (loaded by lib/db.py)
  tests/
  observatory.db   ← SQLite game state (datasets, runs, verdicts)
```

## Pipeline phases

Each dataset progresses through named phases (action_code → action):
- `00-vet`: schema vet (LLM judges metadata + EDA profile)
- `10-eda`: basic EDA (full download, stats, basic charts)
- `15-clean`: data cleaning (parse types, handle missing, flag outliers → rawClean)
- `20-engineer`: feature engineering (create candidate features, cheap MI/zero-variance prune)
- `25-cluster`: regime discovery (multi-view: GMM/KPrototypes/UMAP+HDBSCAN, regime validation)
- `30-select`: feature selection (staged pruning + LLM review, cluster-enriched features)
- `50-report`: publication-ready research report (narrative + modeling with cluster interactions)

Phase registry lives in `lib/artifacts.py:ACTIONS`. Codes use gaps of 10 for easy insertion.
Datasets track `max_action_code` (highest completed) and `cron_actions` (which phases auto-run).

Pipeline replay chain: raw → clean_pipeline.py → pipeline.py → cluster_labels.csv → modeling.
Each downstream agent replays all upstream pipelines before its own work.

## Data sources

- data.gov.sg: v2 metadata API + CKAN-compatible datastore search
- More portals added via configs/portals.yaml

## Rules

- Never present speculative signals as facts
- Always include source attribution and data access date
- Keep a human in the loop for publication decisions
- Respect dataset licenses — check before republishing raw data
- SQL lives in sql/, not embedded in Python
- Raw data stays in data/ (gitignored), metadata in observatory.db
