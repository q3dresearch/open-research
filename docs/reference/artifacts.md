---
title: Artifact Structure
description: Where everything gets written and why
---

# Artifact Structure

```
artifacts/{dataset_id}/
  flags.json                        ← VN route map: which flags are set
  human-notes.md                    ← human steering (edit between runs)

  00-vet-{run_id}.md                ← flat artifact (no run subdir)

  10-eda/
    run-{run_id}/
      charts/                       ← distribution, correlation, category charts
      tables/
        column_assessment.csv       ← per-column: flags, dtype, strategy
        numeric_summary.csv
        value_counts.csv
        correlations.csv
      10-eda-{run_id}.md

  15-clean/
    clean_pipeline.py               ← re-runnable cleaning steps (STEPS list)
    state.json                      ← schema delta after cleaning
    15-clean-{run_id}.md

  20-engineer/
    pipeline.py                     ← cumulative feature engineering (STEPS list)
    state.json                      ← schema delta: added_columns, step_log, samples
    run-{run_id}/
      charts/
      20-engineer-{run_id}.md

  25-cluster/
    cluster_labels.csv              ← one row per data row: cluster_label, cluster_name
    run-{run_id}/
      charts/
        view_comparison.png         ← silhouette comparison across methods
        cluster_sizes.png
        target_by_cluster.png
      cluster_report.json           ← full quality report + LLM review
      25-cluster-{run_id}.md

  30-select/
    run-{run_id}/
      charts/
        s1_cheap_prune.png
        s2_dendrogram.png
        s3_pseudo_target.png
        s4_light_scoring.png
        s5_shap_importance.png
        s6_chart_filter.png
        pipeline_waterfall.png
        correlation_survivors.png
      feature_report.json           ← machine-readable: target, kept, dropped, scores
      feature_scores.csv
      30-select-{run_id}.md

  50-report/
    glossary.json                   ← column lineage: origin, how, intuition, selection outcome
    run-{run_id}/
      report.md                     ← publication-ready narrative
      charts/
        ols_coefficients.png
        partial_resid_{feat}.png
        interaction_{num}_by_{cat}.png
        tree_importance.png
        shap_dep_{feat}.png
      run_metadata.json
```

---

## Pipeline files

Two re-runnable Python files accumulate transforms:

### `clean_pipeline.py`
```python
"""Cumulative cleaning pipeline."""
import pandas as pd
import numpy as np
import re

def step_01_parse_lease(df):
    df['lease_commence_date'] = pd.to_numeric(df['lease_commence_date'], errors='coerce')
    return df

STEPS = [step_01_parse_lease]

def run_pipeline(df):
    for step in STEPS:
        df = step(df)
    return df
```

### `pipeline.py` (engineer)
Same structure, but builds features on top of cleaned data. Any agent that needs engineered features replays both in order: `clean_pipeline.py` → `pipeline.py`.

---

## Replay chain

Every downstream phase re-runs from raw CSV:

```python
# raw → clean → engineer → cluster labels
df = pd.read_csv("data/{id}.csv")
df = clean_mod.run_pipeline(df)      # 15-clean
df = eng_mod.run_pipeline(df)        # 20-engineer
labels = pd.read_csv("cluster_labels.csv")
df["cluster_label"] = labels["cluster_label"].values
```

Never trust cached state — always replay.

---

## Run IDs

Format: `MMDD-HHMMSS` (e.g., `0331-142500`). Chronological ordering without needing full timestamps.

---

## DB tables

| Table | What it tracks |
|-------|---------------|
| `portals` | Portal registry (data.gov.sg, etc.) |
| `datasets` | Dataset state: `max_action_code`, `rejected_at_action` |
| `runs` | Every agent run: action, verdict, LLM response, artifact paths |
| `proposed_joins` | Future: cross-dataset join proposals |
| `synthetic_tables` | Future: joined/derived tables |
