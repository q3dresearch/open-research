# q3d Open Research

Autonomous AI research pipeline over public open datasets. Discovers, vets, analyzes, and produces publication-ready reports — with a human in the loop at every meaningful decision point.

---

## About

q3d is a research system built around a single idea: public data portals contain thousands of datasets that nobody has ever analyzed end-to-end. The pipeline automates the mechanical parts of that work (profiling, cleaning, feature engineering, clustering, modeling) so a researcher can focus on steering and interpreting rather than plumbing.

All outputs are open — charts, reports, and research narratives are committed to this repository.

---

## How It Works

```
Public Data Portal
        │
        ▼
  00  Vet schema        ← LLM judges metadata + 500-row profile
        │
        ▼
  10  EDA               ← Full profile, charts, column assessment
        │
        ▼
  15  Clean             ← Parse types, handle missing, flag outliers → clean_pipeline.py
        │
        ▼
  20  Engineer          ← Iterative feature hypotheses → pipeline.py
        │  ↑
        ▼  │
  25  Cluster           ← Multi-view regime discovery (GMM / KPrototypes / UMAP+HDBSCAN)
        │
        ▼
  30  Select            ← 6-stage feature selection, Track A (predictive) + Track B (structural)
        │
        ▼
  50  Report            ← OLS + LightGBM, publication markdown + column glossary
```

Each phase is driven by a dedicated agent. Every downstream agent **replays** all upstream transforms from the raw CSV — no cached state is trusted.

Human steering happens via `artifacts/{dataset_id}/human-notes.md`. Agents read it before acting.

---

## Installation

Requires Python 3.12+ and an [OpenRouter](https://openrouter.ai) API key.

```bash
git clone https://github.com/q3dresearch/open-research
cd open-research

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# Seed the database (creates tables, registers portals)
python scripts/init_db.py
```

Create `.env` in the repo root:

```
OPENROUTER_API_KEY=sk-or-...
DATA_GOV_SG_API_KEY=...    # optional — removes data.gov.sg rate limits
```

---

## GUI

The Streamlit app is the primary interface for running the pipeline and browsing results.

```bash
streamlit run app/app.py
```

From the sidebar:
- **Add data** — upload a CSV or paste a direct URL
- **Dataset picker** — switch between all vetted datasets
- **Pipeline panel** — one-click Run / Re-run buttons per phase

The main panel shows the latest report first (narrative + charts), then per-phase tabs (EDA tables, cluster radar, feature selection waterfall, column glossary, engineered code).

---

## Running Agents Directly

```bash
python -m agents.vetter <dataset_id>
python -m agents.analyst <dataset_id>
python -m agents.cleaner <dataset_id>
python -m agents.deep_analyst <dataset_id>
python -m agents.clusterer <dataset_id> --target <col>
python -m agents.selector <dataset_id>
python -m agents.reporter <dataset_id>
```

`<dataset_id>` is the data.gov.sg resource ID (e.g. `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`) or a `local_<hash>` for uploaded files.

---

## Philosophy

**Honest failures are valuable.** The pipeline is not optimized toward impressive outputs. Null results, weak models, and "no regime structure found" are valid conclusions. The quality gates (silhouette > 0.3, regime slope p < 0.05) exist to prevent the system from reporting signal that isn't there.

**Good decisions over good predictions.** A feature that explains *why* something happens structurally is preserved even if it adds no predictive power. Feature selection has two tracks: Track A for predictive value, Track B for structural understanding.

**Human in the loop.** Agents read `human-notes.md` before acting. A researcher can steer target variables, flag structural features, and annotate domain context. The pipeline is autonomous but not ungoverned.

**Datasets tell different stories.** Not every dataset supports a full analytical pipeline. The system classifies datasets as `transactional` (row-level, full pipeline), `aggregate` (summary statistics, join enrichment), or `reference` (lookup tables). Each routes to the appropriate pipeline rather than failing. See [Pipeline Types](docs/reference/pipeline-types.md).

---

## Contribution

This is a solo research project at present. Issues and PRs are welcome.

If you want to add a new data portal, edit `configs/portals.yaml`. If you want to contribute a dataset analysis, open a PR with the `artifacts/` outputs and `human-notes.md`.

All data stays in `data/` (gitignored). Only pipeline outputs — reports, charts, glossaries — are committed.

---

## Docs

Full reference docs are built with mkdocs-material:

```bash
.venv/bin/mkdocs serve        # → http://127.0.0.1:8000
.venv/bin/mkdocs gh-deploy    # → https://q3dresearch.github.io/open-research
```
