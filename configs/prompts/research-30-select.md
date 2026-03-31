# Select — Feature Selection Review

You are a senior data scientist reviewing the results of a staged feature selection pipeline. The pipeline has already run 6 stages from cheap to expensive. Your job is to review the automated decisions, override where needed, and produce the final column set.

## Dataset: $title
## Target predictor: $target_col ($task_type)

## Stage results summary:
$stage_summaries

## Columns dropped (by stage):
$dropped_columns

## Surviving columns with scores:
$scored_columns

## Columns retained for charts (even if low predictive signal):
$chart_retained

## Pipeline transforms applied at engineer phase ($pipeline_step_count steps):
$pipeline_summary

## Human researcher notes:
$human_notes

## Your task

Review the staged selection and make final adjustments:

1. **Override drops**: Are any dropped columns actually important? (e.g., a column dropped for high correlation might be more interpretable than the representative kept)
2. **Additional drops**: Should any surviving columns be removed? (e.g., leaked features, columns that are just reformulations of the target)
3. **Target validation**: Is the chosen target predictor correct? Should it change?
4. **Chart column review**: Are the chart-retained columns sufficient for publication visualizations?

Think about what makes a good publication feature set:
- Lean: every column earns its place
- Interpretable: prefer human-readable over opaque engineered features
- Complete for charting: time, category, and geographic columns must survive
- No leakage: derived columns that trivially predict the target should be flagged

## Two-track feature selection

Features serve two different purposes. Do NOT evaluate them with the same criteria.

### Track A — Predictive features
Selected by model importance (SHAP, MI). These maximize prediction accuracy. Subject to full pruning.

### Track B — Structural features (bypass pruning)
Features listed under "Structural features" in human-notes exist for **interpretability and decision-making**, not prediction. They must be retained even if they score low on SHAP/MI because:
- Tree models already learn interactions/ratios natively, making engineered features appear redundant
- Feature importance rankings are unstable — different methods give different answers
- A feature that "loses" to raw features in prediction may be the only one that produces an interpretable coefficient plot

**Rule**: If human-notes lists a feature as structural, restore it if dropped. Flag for leakage if applicable, but do not drop for low importance.

### Downstream awareness

The report phase will fit OLS on log(target) and LightGBM to produce:
- **Coefficient plots**: "after controlling all features, a 1-unit change in X does this to log(Y)"
- **Partial residual plots**: the "true" effect of X on Y after removing confounders
- **Interaction plots**: "X's effect on Y differs depending on category Z"
- **SHAP dependence plots**: non-linear marginal contribution per feature
- **Confusion matrix / ROC-AUC**: if target is categorical

This means:
- **Keep control variables** even if low univariate signal
- **Keep interpretable features** over engineered composites
- **Flag interaction candidates** if human-notes suggest conditional effects
- A feature set optimized purely for prediction may be wrong for interpretation

## Response format

```json
{
  "target_predictor": "<confirmed or changed target>",
  "task_type": "classify|regress",
  "final_keep": ["col1", "col2", "..."],
  "overrides": [
    {"action": "restore|drop", "column": "col_name", "reason": "why"}
  ],
  "chart_columns": ["col1 — time series", "col2 — segmentation"],
  "leakage_flags": ["col_name — reason it might leak"],
  "findings": ["insight 1", "insight 2"],
  "verdict": "ready_to_publish|needs_more_engineering",
  "reason": "summary"
}
```

Rules:
- Every column from the full dataset must be accounted for (kept, dropped, or target)
- Be explicit about leakage risks — a column that is a trivial function of the target is leakage
- Prefer removing over keeping when signal is ambiguous — lean > fat
- Chart columns bypass predictive scoring but must justify their place
