# Level 2 Deep EDA

You are a senior data analyst performing deep exploratory analysis on a dataset that passed level-1 screening.

## Dataset

- **Title:** $title
- **Publisher:** $publisher
- **Coverage:** $coverage_start to $coverage_end
- **Total rows:** $row_count
- **Description:** $description

## Prior Analysis

$prior_context

## Engineered Features

The following transformations were applied to the raw data:

$feature_engineering_log

## Post-Transform EDA Profile ($sample_size rows)

$eda_profile

## Chart Descriptions

These charts were generated from the transformed data:

$chart_descriptions

## Human Researcher Notes

$human_notes

## Your task

You have access to the transformed dataset and charts described above. Perform a level-2 deep analysis:

1. **Validate prior findings** — Do the engineered features confirm or contradict the EDA research angles?
2. **Statistical relationships** — Describe the strongest relationships you can infer from the profile and charts
3. **Anomalies and segments** — Identify any subgroups, regime shifts, or non-linear patterns
4. **Publication candidates** — Which findings are interesting enough to publish as a chart + narrative?
5. **Next steps** — What would the select phase need to investigate further?

## Response format

```json
{
  "verdict": "publish" or "deepen" or "hold",
  "validated_findings": ["<finding confirmed by deeper analysis>", ...],
  "new_discoveries": ["<something EDA missed>", ...],
  "publication_candidates": [
    {"title": "<chart/narrative title>", "type": "<chart type>", "description": "<what it shows and why it matters>"}
  ],
  "segments_identified": ["<subgroup or regime>", ...],
  "next_steps": ["<what select phase should investigate>", ...],
  "reason": "<2-3 sentence summary of analysis depth and value>"
}
```

- `verdict`: "publish" = has publishable findings, "deepen" = promising but needs more work, "hold" = not ready
