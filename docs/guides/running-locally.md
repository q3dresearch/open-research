---
title: Running Locally
description: Setup and local development
---

# Running Locally

## Setup

```bash
# Clone
git clone https://github.com/q3dresearch/open-research
cd open-research

# Create venv
python3 -m venv .venv
source .venv/bin/activate

# Install deps
pip install -r requirements.txt
```

## Database

SQLite — no server needed. Initialised automatically on first run:

```bash
python -m lib.db  # creates observatory.db
```

Schema lives in `sql/schema.sql`. Never modify the DB directly — all writes go through agents.

## Environment

Create `.env` (gitignored):

```bash
OPENROUTER_API_KEY=sk-or-...
```

The LLM client (`lib/llm.py`) reads this via `python-dotenv`.

## Viewing docs locally

```bash
# From repo root
.venv/bin/mkdocs serve
# → http://127.0.0.1:8000
```

## Deploy docs to GitHub Pages

```bash
.venv/bin/mkdocs gh-deploy
# → https://q3dresearch.github.io/open-research
```

## Data directory

Raw CSVs go in `data/` — gitignored, never committed. If you're on a new machine, re-run `vetter` or `analyst` to re-download.

## Artifacts

`artifacts/` contains run markdown, pipelines, charts. Committed to the repo for audit trails. Charts (PNG) can be gitignored if storage is a concern.

## Stack

| Dep | Purpose |
|-----|---------|
| pandas | Data manipulation |
| scikit-learn | Clustering, selection |
| lightgbm | Tree modeling |
| shap | Feature importance |
| statsmodels | OLS regression |
| hdbscan | Density clustering |
| umap-learn | Manifold embedding |
| matplotlib | Charts |
| httpx | Portal API calls |
| mkdocs-material | This docs site |
