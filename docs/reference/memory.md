---
title: Memory System
description: How agents remember what they tried, learned, and found
---

# Memory System

Each pipeline run generates more artifacts than can fit in a model's context window.
The memory system gives agents a structured way to remember what happened across runs,
without loading full artifact files into the prompt.

---

## Structure

```
memory/
  main/
    SOUL.md        ← research identity — always loaded into every agent
    AGENTS.md      ← operational rules — always loaded
    TOOLS.md       ← arsenal reference — always loaded
  {dataset_id}/
    00-vet.md      ← journal of all vet runs for this dataset
    10-eda.md
    15-clean.md
    20-engineer.md
    25-cluster.md
    30-select.md
    50-report.md
    index.json     ← artifact map: columns, tables, charts, concerns
```

---

## Phase Journals

Each time an agent runs a phase, it appends to `memory/{dataset_id}/{phase}.md`.
The journal captures what was tried, what succeeded, and what concerns carry forward.

**Format:**

```markdown
## Run run-0401-142500  _2026-04-01 14:25 UTC_

### plan
The dataset has a strong geographic dimension. town is high-cardinality categorical —
rather than encoding it directly, a market_premium_index (town median / global median)
would give a continuous signal that captures location premium without the cardinality...

**→** hypothesis: "market_premium_index + lease_remaining_years", 3 steps planned

### step_create_market_premium_index (compute town-level price premium ratio)
Computing ratio of town median to global median using groupby + transform. This avoids
look-ahead bias issues since we're working with historical data only...

**→** OK: +1 col (market_premium_index)

### eval
Both features show strong signal. market_premium_index (0.72 correlation) dominates.
Concern: it is derived from resale_price — may cause leakage in modeling...

**→** verdict: continue — 2 features added, leakage concern flagged for selection
```

The agent's reasoning before the JSON block (chain-of-thought) is captured at each
LLM call and appended immediately. This means re-running phase 3 of engineer can read
what runs 1 and 2 tried and why they succeeded or failed.

---

## Artifact Index

`memory/{dataset_id}/index.json` is the agent's mental map — a compact summary of
everything produced so far. Agents load this with every phase to know what exists
without reading the full artifacts.

```json
{
  "columns": {
    "market_premium_index": {
      "phase": "20-engineer",
      "run": "run-0401-142500",
      "how": "town median resale_price / global median",
      "intuition": "captures town-level price premium relative to market",
      "caveat": "derived from target — possible leakage",
      "dtype": "float64",
      "summary": "mean=1.08, std=0.34, range [0.41, 2.31]"
    }
  },
  "tables": {
    "anova_town": {
      "path": "10-eda/run-0331-142500/tables/anova_town.csv",
      "summary": "F=1247, p<0.001, town explains 38% of price variance",
      "phase": "10-eda"
    }
  },
  "charts": {
    "cluster_radar": {
      "path": "25-cluster/run-0401-091200/charts/cluster_radar.png",
      "finding": "3 regimes: premium towns (C0), mid-range (C1), budget (C2)",
      "tier": "finding",
      "phase": "25-cluster"
    },
    "qqplot_resale_price": {
      "path": "10-eda/run-0331/charts/qqplot_resale_price.png",
      "finding": "heavy right tail, log-transform needed",
      "tier": "diagnostic",
      "phase": "10-eda"
    }
  },
  "concerns": [
    {"phase": "20-engineer", "text": "market_premium_index derived from target"},
    {"phase": "25-cluster", "text": "silhouette 0.42 — acceptable but not strong"}
  ]
}
```

**`tier` on charts** separates findings (show the human) from diagnostics (audit trail).
Streamlit shows `finding` tier by default; `diagnostic` behind an expander.

**Agents never read full artifact files into context.** They read the index
(which fits in context) and call tools to get cheap slices when they need detail.

---

## Chain-of-Thought in Notebooks

Every LLM call in the pipeline uses `call_llm_traced()`, which captures the model's
reasoning before the JSON block. This reasoning flows to two places:

1. **`memory/{dataset_id}/{phase}.md`** — appended immediately, survives across sessions
2. **`session.ipynb`** — added as collapsible `[COT]` markdown cells

In the notebook, each step appears as:

```
[COT] plan

<details>
<summary>Model reasoning</summary>

The dataset has a strong geographic dimension...
[full chain-of-thought]

</details>
```

This lets a researcher audit exactly what the agent was thinking at each step.

---

## `memory/main/` — Identity Files

Files in `memory/main/` are committed to the repo and loaded into every agent run.

| File | Purpose |
|------|---------|
| `SOUL.md` | Research identity — "I am a quantitative researcher who values statistical rigor..." |
| `AGENTS.md` | Operational rules — "Never present a chart without stating what hypothesis it tests..." |
| `TOOLS.md` | Arsenal reference — how and when to use each function in `lib/eda/` |

These are the equivalent of OpenClaw's workspace configuration files. Edit them to
change how the agent reasons about any dataset.

---

## Gitignore

Per-dataset memory journals are local (gitignored). Only `memory/main/` is committed.

```gitignore
memory/*
!memory/main
!memory/main/**
```

This means each user's analysis history is private, while shared identity files are versioned.
