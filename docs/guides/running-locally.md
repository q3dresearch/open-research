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

# Initialise the database (seeds portals, creates tables)
python scripts/init_db.py
```

## Database

SQLite — no server needed. Schema lives in `sql/schema.sql`.

`observatory.db` is gitignored (it's runtime state per user). Seed it fresh with:

```bash
python scripts/init_db.py
```

Never modify the DB directly — all writes go through agents.

## Environment

Create `.env` (gitignored):

```bash
OPENROUTER_API_KEY=sk-or-...
DATA_GOV_SG_API_KEY=...    # optional — removes data.gov.sg rate limits
```

## Register the Jupyter kernel (once)

The session notebooks run in the project venv:

```bash
source .venv/bin/activate
python -m ipykernel install --user --name q3d-research --display-name "q3d Research (.venv)"
```

## Launch the GUI

The Streamlit app lets you ingest datasets, run phases, and browse artifacts:

```bash
streamlit run app/app.py
```

Paste your `OPENROUTER_API_KEY` in the sidebar (or set it in `.env`).

## Running agents directly

```bash
python -m agents.vetter <dataset_id>
python -m agents.analyst <dataset_id>
python -m agents.cleaner <dataset_id>
python -m agents.deep_analyst <dataset_id>
python -m agents.clusterer <dataset_id> --target <col>
python -m agents.selector <dataset_id>
python -m agents.reporter <dataset_id>
```

## Artifacts and data

| Path | Status | Notes |
|------|--------|-------|
| `data/` | gitignored | Raw CSVs — re-download via agents |
| `artifacts/` | gitignored | Generated pipeline outputs |
| `observatory.db` | gitignored | Runtime DB state |
| `session.ipynb` | inside `artifacts/` | Jupyter notebook per dataset |

Re-run from scratch on a new machine: `python scripts/init_db.py`, then run agents against any dataset ID.

## Viewing docs locally

```bash
# From repo root (mkdocs-material must be installed)
.venv/bin/mkdocs serve
# → http://127.0.0.1:8000
```

## Deploy docs to GitHub Pages

```bash
.venv/bin/mkdocs gh-deploy
# → https://q3dresearch.github.io/open-research
```

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
| streamlit | GUI app |
| nbformat | Notebook builder |
| mkdocs-material | This docs site |
