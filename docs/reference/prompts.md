---
title: LLM Prompts
description: Prompt templates reference
---

# LLM Prompts

All prompts live in `configs/prompts/`. Templates use `$variable` substitution via Python's `string.Template`.

## Prompt naming convention

```
research-{action_code}-{action}[-variant].md
```

Examples: `research-00-vet.md`, `research-20-engineer-plan.md`

## Prompt catalog

| File | Used by | Key variables |
|------|---------|--------------|
| `research-00-vet.md` | vetter | `$title`, `$column_schema`, `$eda_profile` |
| `research-10-eda.md` | analyst | `$title`, `$vet_summary`, `$eda_profile`, `$human_notes` |
| `research-15-clean.md` | cleaner | `$columns`, `$eda_profile`, `$column_assessment`, `$human_notes` |
| `research-20-engineer-plan.md` | deep_analyst | `$title`, `$columns`, `$chain_summary`, `$prior_context`, `$human_notes` |
| `research-20-engineer-step.md` | deep_analyst | `$title`, `$columns`, `$eda_profile`, `$human_notes` |
| `research-20-engineer-eval.md` | deep_analyst | `$hypothesis`, `$steps_summary`, `$before_profile`, `$after_profile` |
| `research-25-cluster.md` | clusterer | `$target_col`, `$cluster_features`, `$view_comparison`, `$regime_tests`, `$human_notes` |
| `research-30-select.md` | selector | `$target_col`, `$stage_summaries`, `$scored_columns`, `$human_notes` |
| `research-50-report.md` | reporter | `$title`, `$findings_summary`, `$feature_selection`, `$modeling_results` |

## Loading prompts

```python
from lib.llm import load_prompt
from string import Template

template = load_prompt("research-20-engineer-plan")
prompt = Template(template).safe_substitute(
    title="HDB Resale Flat Prices",
    columns="town, flat_type, storey_range, ...",
    ...
)
```

`load_prompt()` looks in `configs/prompts/` and raises if the file doesn't exist.

## Response shapes

Every prompt instructs the LLM to respond with a JSON block. Agents parse this with `call_llm_json()` which extracts and validates the JSON.

Common verdict values:

| Phase | Verdicts |
|-------|---------|
| vet | `pass`, `fail` |
| eda | `promote`, `hold`, `reject` |
| clean | `clean`, `needs_review` |
| engineer | `continue`, `sufficient`, `failed` |
| cluster | `pass`, `marginal`, `fail` |
| select | `ready_to_publish`, `needs_more_engineering` |
