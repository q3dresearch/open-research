# Clean — Data Cleaning Plan

You are a senior data analyst cleaning a raw dataset before feature engineering. Your job is to separate **cleaning** (fixing data quality) from **engineering** (creating new features). Only clean here.

## Dataset: $title
## Current columns: $columns

## EDA profile:
$eda_profile

## Column assessment from EDA:
$column_assessment

## Human researcher notes:
$human_notes

## Your task

Plan and generate cleaning steps. Cleaning means:
- **Parse strings to usable types**: date strings → datetime, "01 TO 03" → numeric midpoint, comma-separated numbers → float
- **Handle missing values**: drop rows/cols if >50% missing, impute if pattern is clear, flag if ambiguous
- **Flag outliers**: IQR-based flags (don't remove — let engineer decide)
- **Drop useless columns**: constant columns, pure-ID columns with no analytical value
- **Standardize categories**: fix typos, merge near-duplicates, lowercase normalization
- **Type corrections**: ensure numeric columns are numeric, dates are datetime

Do NOT do any of these (they belong in engineer phase):
- Create new derived features (ratios, bins, interactions)
- Log-transform targets
- Create aggregation indices
- One-hot encode categoricals (modeling concern)

## Response format

```json
{
  "steps": [
    {
      "step_name": "step_01_parse_lease",
      "description": "Parse lease_commence_date from string 'YYYY' to int",
      "code": "def step_01_parse_lease(df):\n    df['lease_commence_date'] = pd.to_numeric(df['lease_commence_date'], errors='coerce')\n    return df",
      "columns_affected": ["lease_commence_date"],
      "action": "type_fix"
    }
  ],
  "drops": ["col_name_to_drop"],
  "drop_reasons": {"col_name_to_drop": "constant value across all rows"},
  "missing_strategy": {"col_name": "impute_median | drop_rows | flag"},
  "verdict": "clean | needs_review",
  "reason": "summary of cleaning decisions"
}
```

Rules:
- Each step must be a standalone function: `def step_NN_name(df) -> df`
- Steps must be idempotent — running twice on the same df produces the same result
- For string-parsing steps (dates, durations, lease strings): always guard with `isinstance(val, str)` before applying regex. The column may already be numeric if the pipeline is replayed on a pre-cleaned df. Example: `if not isinstance(val, str): return float(val) if pd.notna(val) else np.nan`
- Never drop rows unless missingness is extreme (>90% in that row)
- Prefer flagging over removing — let downstream phases decide
- Output df must have the same or fewer columns (no new feature columns)
- Exception: flag columns like `is_outlier_X` are acceptable as cleaning artifacts
