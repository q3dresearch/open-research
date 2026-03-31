# Level 2 — Evaluate Run

You just completed a multi-step investigation run on a dataset. Review what was found.

## Dataset: $title
## Hypothesis tested: $hypothesis

## Steps executed in this run:
$steps_summary

## Profile BEFORE this run ($before_cols columns):
$before_profile

## Profile AFTER this run ($after_cols columns):
$after_profile

## Chart descriptions (generated from post-run data):
$chart_descriptions

## Prior runs:
$chain_summary

## Human notes:
$human_notes

## Your task

1. Did the steps confirm, disprove, or fail to resolve the hypothesis?
2. What concrete findings emerged from this run?
3. Do the charts reveal anything unexpected?
4. What should the NEXT run investigate (if continuing)?

## Response format

```json
{
  "verdict": "continue" or "sufficient" or "failed",
  "hypothesis_result": "confirmed" or "disproved" or "inconclusive",
  "findings": ["<what we learned>", ...],
  "anomalies": ["<anything unexpected>", ...],
  "next_hypothesis": "<what the next run should test, if continuing>",
  "reason": "<2-3 sentence summary of this run's outcome>"
}
```

- `continue`: more runs needed — the hypothesis opened new questions
- `sufficient`: analysis has enough depth for meaningful publication
- `failed`: the steps produced garbage or the data can't support this analysis
