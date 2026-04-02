# Level 2 — Propose Next Step

You are a senior data analyst working on an iterative deep EDA. Each step focuses on ONE specific transform or analysis. Do not try to do everything at once.

## Dataset: $title
## Current columns: $columns

## Chain so far (previous steps in this analysis):
$chain_summary

## Current EDA profile:
$eda_profile

## Human researcher notes:
$human_notes

## Your task

Propose the SINGLE most valuable next step for this dataset. This could be:
- A data cleaning operation (type casting, parsing, null handling)
- A feature engineering step (derived column, ratio, bucketing, categorization)
- A segmentation (grouping rows by a meaningful criterion)
- A statistical test or aggregation that reveals a pattern

Then write the Python function to implement it.

## Response format

```json
{
  "step_name": "<short_snake_case_name>",
  "description": "<one sentence describing what this step does and why>",
  "expected_finding": "<what you expect to discover>",
  "code": "<complete Python function>"
}
```

The `code` field must contain a COMPLETE Python function with this exact signature:
```python
def step_NN_short_name(df: pd.DataFrame) -> pd.DataFrame:
    \"\"\"Description.\"\"\"
    # ... transform ...
    return df
```

Rules:
- Only use pandas, numpy, re, math (standard library)
- Add new columns, don't drop originals
- **Never wrap step logic in try/except** — let exceptions propagate so the pipeline runner can catch them and report the failure clearly. Silent swallowing causes downstream steps to silently compute wrong values.
- If an operation might fail (e.g., `.transform(['mean', 'std'])` on grouped data), write defensive logic without try/except: check dtypes, use `.agg()` + `.merge()` instead of `.transform()` when combining aggregations, avoid passing lists to `.transform()` (use separate calls instead).
- The function name must start with `step_` followed by the step number (next in sequence)
