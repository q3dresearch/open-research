---
title: Loading Datasets
description: How to add a new dataset and run it through the pipeline
---

# Loading Datasets

## From data.gov.sg

Dataset IDs look like `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`. Find them in the URL of any dataset page.

### Step 1 — Vet the schema

```bash
python -m agents.vetter <dataset_id>
```

Downloads 500 rows, runs EDA profile, asks LLM to judge. Creates:

- `artifacts/{id}/00-vet-{run_id}.md`
- `artifacts/{id}/human-notes.md` (stub for your notes)
- DB entry in `datasets` + `runs` tables

If verdict is `fail`, the dataset is rejected and won't advance.

### Step 2 — EDA

```bash
python -m agents.analyst <dataset_id>
```

Downloads full CSV (if not cached), produces charts and profile tables including `column_assessment.csv`.

### Step 3 — Edit human-notes.md

Before cleaning and engineering, add your domain knowledge:

```markdown
# Human Notes: HDB Resale Flat Prices

## Target
target: resale_price

## Structural features (do not drop for low importance)
- price_per_sqm: unit economics for cross-size comparison
- lease_bucket: domain threshold, 60-year cliff effect
- town_tier: geographic hierarchy for interaction analysis

## Context an agent wouldn't know
- Lease policy: HDB flats lose value steeply below 60 years remaining
- Town tiers: Core Central Region commands a premium over Outside Central Region
```

### Step 4 — Clean

```bash
python -m agents.cleaner <dataset_id>
```

LLM proposes cleaning steps, executes them, saves `clean_pipeline.py`.

### Step 5 — Engineer features

```bash
python -m agents.deep_analyst <dataset_id>
# Runs 3 investigation runs by default
python -m agents.deep_analyst <dataset_id> --max-runs 5  # more runs
```

### Step 6 — Discover regimes

Requires a target column (from human-notes or --target flag):

```bash
python -m agents.clusterer <dataset_id> --target resale_price
```

### Step 7 — Select features

```bash
python -m agents.selector <dataset_id>
# With explicit target:
python -m agents.selector <dataset_id> --target resale_price
```

### Step 8 — Generate report

```bash
python -m agents.reporter <dataset_id>
```

---

## Checking progress

```python
from lib.flags import print_route_map
print_route_map("<dataset_id>")
```

Output:
```
============================================================
  Route Map: d_8b84c4ee58e3cfc0ece0d773c8ca6abc
  Flags: 14/22
============================================================
  ## 00-vet: completed [schema_vetted]
  ## 10-eda: completed [eda_profiled, column_assessment_exists]
  ## 15-clean: completed [types_parsed, missing_handled]
  >> 20-engineer: unlocked
  XX 25-cluster: locked (needs: candidate_features_created)
  XX 30-select: locked (needs: candidate_features_created, target_identified)
  XX 50-report: locked (needs: features_selected, target_identified)
```

Icons: `##` = completed, `>>` = unlocked (ready to run), `XX` = locked (missing flags).

---

## Speed-running

You can skip the cluster phase if there's no clear target or you want faster results:

```bash
python -m agents.vetter <id>
python -m agents.analyst <id>
python -m agents.cleaner <id>
python -m agents.deep_analyst <id>
python -m agents.selector <id> --target <col>
python -m agents.reporter <id>
```

Speed-run skips regime discovery but still produces a valid report. Add cluster later when you have a target.

---

## Steering agents with human-notes

Every agent reads `artifacts/{id}/human-notes.md` before acting. Edit it between runs to steer the next phase.

See [Human Notes guide](human-notes.md) for what each section does.
