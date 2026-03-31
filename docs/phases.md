---
title: Phase Reference
description: Complete reference for all seven pipeline phases
---

# Phase Reference

All phases derive their constants from `lib/artifacts.py:ACTIONS`. Never hardcode action codes.

## Phase registry

```python
ACTIONS = {
    "00": "vet",
    "10": "eda",
    "15": "clean",
    "20": "engineer",
    "25": "cluster",
    "30": "select",
    "50": "report",
}
```

Gaps of 10 between codes allow inserting new phases without renumbering.

---

## 00 — vet

**Agent**: `agents/vetter.py` | **Prompt**: `research-00-vet`

Schema quality gate. LLM judges dataset metadata + 500-row EDA profile.

**Flags set on pass**: `schema_vetted`

**LLM response**:
```json
{
  "verdict": "pass | fail",
  "score": 8,
  "reason": "...",
  "research_angles": ["..."],
  "concerns": ["..."]
}
```

---

## 10 — eda

**Agent**: `agents/analyst.py` | **Prompt**: `research-10-eda`

Full EDA. Produces charts, profile tables, column assessment CSV.

**Flags set**: `eda_profiled`, `column_assessment_exists`

**Outputs**:

- `10-eda/run-{id}/charts/` — distribution, correlation, category charts
- `10-eda/run-{id}/tables/column_assessment.csv` — per-column flags + strategy

---

## 15 — clean

**Agent**: `agents/cleaner.py` | **Prompt**: `research-15-clean`

Data quality cleanup. Produces `clean_pipeline.py` — re-runnable from raw CSV.

**Flags set**: `types_parsed`, `missing_handled`, optionally `outliers_flagged`

**Boundary rule**: clean produces rawClean (same or fewer columns, fixed types). No new features.

What belongs here:

- Parse string dates → datetime
- Parse `"01 TO 03"` → numeric midpoint
- Flag IQR outliers as `is_outlier_X`
- Drop constant/ID-only columns
- Standardize category strings

What does NOT belong here (→ engineer):

- Log transforms, ratios, bins
- Interaction terms
- Aggregation indices

---

## 20 — engineer

**Agent**: `agents/deep_analyst.py` | **Prompts**: `research-20-engineer-{plan,step,eval}`

Iterative feature engineering. Each invocation runs 1–3 investigation runs.

**Flags set**: `candidate_features_created`, `cheap_prune_done` (on sufficient verdict)

**Run loop**:
```
plan (hypothesis) → execute steps → generate charts → evaluate
      ↑___________________________|  (loop if continue)
```

**Replay chain**: raw → `clean_pipeline.py` → `pipeline.py`

---

## 25 — cluster

**Agent**: `agents/clusterer.py` | **Prompt**: `research-25-cluster`

Multi-view regime discovery. Three methods see different shapes of structure:

| Method | Sees | Misses |
|--------|------|--------|
| GMM | Elliptical, covariance-aware | Nonlinear, mixed data |
| KPrototypes | Mixed data (numeric + categorical) | Nonlinear, elliptical |
| UMAP + HDBSCAN | Nonlinear manifolds, arbitrary shapes | May leave noise unassigned |

**Regime validation**: for each feature, tests `target ~ feature * cluster` — significant interaction = different slopes = genuine regime.

**Flags set**: `clusters_discovered`, `regime_validated`, `cluster_label_added`

**Target resolution** (in order, no guessing):

1. `--target` CLI flag
2. `target: <col>` in human-notes.md
3. Prior select phase `feature_report.json`
4. Prior EDA LLM response

**Quality gates** to pass:

- [ ] Silhouette > 0.3
- [ ] No cluster < 5% of data
- [ ] At least one feature with slope p < 0.05

---

## 30 — select

**Agent**: `agents/selector.py` | **Prompt**: `research-30-select`

6-stage feature selection pipeline, then LLM review.

**Flags set**: `target_identified`, `features_selected`, optionally `structural_features_preserved`

**Stages**:

1. Cheap prune (missingness, variance, ID-like)
2. Correlation clustering (keep one representative per correlated group)
3. Pseudo-target redundancy (predict each column from others)
4. Light supervised scoring (MI + correlation with target)
5. SHAP importance (LightGBM)
6. Chart filter (retain time/category for publication)

**Two-track selection**:

- **Track A** — predictive, subject to full pruning
- **Track B** — structural, listed in `human-notes.md`, bypass pruning

**Replay chain**: raw → `clean_pipeline.py` → `pipeline.py` → `cluster_labels.csv`

---

## 50 — report

**Agent**: `agents/reporter.py` | **Prompt**: `research-50-report`

Publication-ready report with OLS + LightGBM modeling.

**Flags set**: `ols_fitted`, `tree_fitted`, `report_generated`

**Model charts generated**:

- OLS coefficient plot
- Partial residual plots (top 2 features)
- Interaction plot (top numeric × top categorical)
- LightGBM feature importance
- SHAP dependence plot (top feature)

**Replay chain**: raw → `clean_pipeline.py` → `pipeline.py` → `cluster_labels.csv` → modeling
