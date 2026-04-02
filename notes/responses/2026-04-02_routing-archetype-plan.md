# Routing + Archetype Plan
_2026-04-02 — awaiting human review_

---

## Context for classification — what signals the EDA LLM gets

| Signal | Source | Weight |
|---|---|---|
| `row_count` | profile | High — <500 rows almost never transactional |
| `numeric_col_count` / `categorical_col_count` ratio | profile | High — pivot tables are mostly numeric |
| `unique_count` per categorical column | profile col dtypes | High — 3-5 unique values = category dimension, not entity |
| presence of a year/date column | profile col dtypes | High — time axis present → time_series or panel |
| `pipeline_type` from vetter | DB | Medium — rough prior, not authoritative |
| column names (`rate_`, `pct_`, `total_`, `avg_`) | schema | Medium — naming conventions signal pre-aggregation |
| `vet_summary` research_angles | DB | Low — directional only |

### Confidence tiers

- **High confidence** (deterministic, no LLM ambiguity): `row_count < 200` AND all/mostly numeric → `aggregate_pivot`. `row_count < 50` → `reference` or `aggregate_summary`.
- **Medium confidence** (LLM weighs signals): `row_count 200–2000` + mixed shape/naming signals.
- **Low confidence** → archetype = `unknown`, `research_mode = descriptive` as safe fallback. Cheaper to run descriptive on a transactional than predictive on a pivot.

---

## Analytics sequence per archetype

Key principle: **low degrees of freedom = deterministic sequence.** When a dataset has 2-3 categorical dimensions and 1-2 value columns, the entire analysis space is enumerable — no LLM creativity needed mid-sequence. LLM only interprets results at the end.

| Archetype | DoF | Agent role | Sequence |
|---|---|---|---|
| `aggregate_pivot` | Very low | Deterministic | group sizes → composition bars → trend lines by category → variance decomposition → marginal effects bar → OLS on category dummies |
| `aggregate_summary` | Low | Mostly deterministic | same as pivot + YoY delta chart |
| `time_series` | Low | Deterministic | trend line → AR forecast → seasonality decomposition → anomaly annotation |
| `cross_section` | Medium | Semi-creative | distribution per column → correlation heatmap → optional clustering if >500 rows |
| `transactional` | High | Creative (full pipeline) | clean → engineer → cluster → select → model |
| `panel` | High | Creative | same as transactional + fixed-effects model |

---

## Proposed `lib/routing.py` interface

```python
ARCHETYPE_SEQUENCE = {
    "aggregate_pivot": [
        "describe_group_sizes",
        "composition_bars",
        "trend_lines_by_category",
        "variance_decomposition",
        "marginal_effects_bar",
        "ols_summary",
    ],
    "aggregate_summary": [...],
    "time_series": [
        "trend_line",
        "ar_forecast",
        "seasonality_decomposition",
        "anomaly_annotation",
    ],
    "cross_section": [...],
    "transactional": None,   # None = full creative pipeline (existing path)
    "panel": None,
    "unknown": "descriptive", # safe fallback
}

def get_analytics_sequence(archetype: str, research_mode: str) -> list[str] | None:
    """Return ordered list of analysis functions, or None for full creative pipeline."""
    ...

def should_run_creative_pipeline(archetype: str) -> bool:
    """True only for transactional and panel."""
    ...
```

Each string maps to a function in `lib/eda/describe.py`. EDA runs the sequence after archetype is classified. No LLM decisions mid-sequence.

---

## Questions for human

1. **Archetype taxonomy** — are `panel` and `cross_section` distinct enough to warrant separate sequences, or collapse into `transactional`?
2. **OLS on aggregate_pivot** — drug_arrests has only ~360 rows and 4 columns. OLS on category dummies is deterministic and produces marginal effects. Agree this is the right "model" for this archetype rather than LightGBM?
3. **AR forecast scope** — in scope for `time_series` archetype in this sprint? Requires `statsmodels`. Already installed in venv?
4. **`unknown` fallback** — agree that `descriptive` is the safe default for unclassified datasets rather than attempting predictive?
5. **Routing location** — `lib/routing.py` as a standalone module, or fold into `lib/artifacts.py` alongside the ACTIONS registry?
