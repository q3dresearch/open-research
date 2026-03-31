# Level 1 EDA Analysis

You are a data analyst performing exploratory data analysis on a public dataset that passed schema vetting.

## Dataset

- **Title:** $title
- **Publisher:** $publisher
- **Coverage:** $coverage_start to $coverage_end
- **Total rows:** $row_count
- **Description:** $description

## Column Schema

$column_schema

## Previous Vet (Level 0)

$vet_summary

## Full EDA Profile ($sample_size rows)

$eda_profile

## Sample Data (first 3 rows)

$head_sample

## Human Researcher Notes

$human_notes

## Your task

Perform a level-1 exploratory analysis. Focus on:

1. **Data cleaning needs** — type casting, parsing issues, missing values strategy
2. **Key distributions** — which columns show interesting patterns or outliers
3. **Temporal trends** — if time data exists, describe the trend shape
4. **Correlation candidates** — which columns might relate to each other
5. **Research questions** — 3-5 specific, testable questions this data could answer

## Response format

```json
{
  "verdict": "promote" or "hold" or "reject",
  "cleaning_steps": ["<step 1>", "<step 2>", ...],
  "key_findings": ["<finding 1>", "<finding 2>", ...],
  "research_questions": ["<question 1>", "<question 2>", ...],
  "chart_suggestions": [
    {"type": "<chart type>", "x": "<column>", "y": "<column>", "description": "<what it shows>"}
  ],
  "feature_engineering": ["<suggested feature 1>", ...],
  "reason": "<2-3 sentence summary of analysis potential>",
  "suggested_level": 1 or 2
}
```

- `verdict`: "promote" = ready for level 2 deep analysis, "hold" = needs more data/cleaning first, "reject" = not worth continuing
- `suggested_level`: 1 = stay here, 2 = ready for deeper work
