# Product Requirements Document
<!-- version: 0.1 | phase: 1 | last-updated: 2026-03-24 -->
<!-- changelog:
  v0.1 - Initial PRD from Phase 1 Q&A
-->

## Overview

**Project:** open-research
**One-liner:** AI agent that autonomously discovers, vets, and analyzes public datasets from CKAN portals, producing publication-ready charts and recurring alerts when indicators move.
**Target user:** Operator/researcher (self) first; downstream: data-curious citizens, urbanists, policy teams.

## Problem Statement

### The Problem

Public open-data portals (CKAN, data.gov.sg, openAFRICA, etc.) contain thousands of datasets. Most are never analyzed beyond basic downloads. The barrier isn't access — it's the labor of evaluating which datasets are worth researching, running meaningful analysis, and maintaining that analysis over time as data updates.

A solo researcher cannot manually vet thousands of schemas, run EDA on hundreds of tables, and maintain recurring publications. The work is repetitive, structured, and perfect for AI automation — but no tool exists that does the full loop.

### Current Solutions & Why They Fail

| Solution | Why it fails |
|---|---|
| Manual EDA (notebooks) | Doesn't scale past 5-10 datasets. No systematic vetting. |
| AutoEDA libraries (ydata-profiling, sweetviz) | Produces generic stats (min/max/median) with no judgment. Can't tell you "this dataset is boring." |
| AI chat tools (Julius, EDA-GPT) | User-driven — you must upload data and ask questions. Not autonomous. |
| CKAN built-in previews | Minimal — shows a table preview, no analysis. |
| Auctus (NYU) | Finds joinable datasets but doesn't analyze them. |
| datHere AI chatbot | Portal-scoped Q&A — doesn't proactively research or publish. |

### Our Angle

An **autonomous research loop** where the AI:
1. Crawls portal catalogs and judges dataset quality from schema alone (cheap filter)
2. Downloads and runs escalating tiers of EDA (expensive but only on survivors)
3. Produces publication-ready artifacts (charts, narratives)
4. Re-runs on a schedule matching the dataset's update frequency
5. Proposes cross-dataset joins for higher-signal research
6. Builds institutional memory from past decisions (positive/negative examples)

## Core Value Proposition

An operator adds a portal URL. The AI autonomously vets every dataset, graduates the good ones through research tiers, and produces recurring publications — with full auditability via Jupyter notebooks and decision logs.

## User Stories

| Priority | User Story | Acceptance Criteria |
|---|---|---|
| P0 | As an operator, I want to add a CKAN portal URL and have the AI catalog all datasets | Portal's dataset list stored in SQLite with schema metadata |
| P0 | As an operator, I want the AI to automatically judge which datasets are worth researching | research-00-schema-vet prompt runs on each schema; pass/fail + reasoning saved |
| P0 | As an operator, I want basic EDA run on datasets that pass schema vetting | research-01-lv1-eda runs; results saved as notebook + decision log |
| P0 | As an operator, I want to see why the AI rejected or accepted a dataset | Decision logs with head/tail samples, schema shape, LLM reasoning saved per dataset |
| P0 | As an operator, I want publication-ready charts from graduated datasets | Charts (trend lines, histograms, heatmaps) saved as images with source attribution |
| P1 | As an operator, I want advanced EDA (feature engineering, transforms, panel conversion) on lv1 survivors | research-02-lv2-eda runs; transformed data + signals saved |
| P1 | As an operator, I want graduated datasets re-analyzed on a schedule | Cron config per dataset; re-runs produce new artifacts + diff against previous |
| P1 | As an operator, I want the AI to propose cross-dataset joins | JoinProposal table in SQLite; proposed joins re-run through the same tier system |
| P2 | As a consumer, I want to browse published research outputs on the web | open-research repo serves as static site or datasette instance |
| P2 | As an operator, I want past decisions used as context for future vetting | Artifact feedback loop: good/bad examples injected into vetting prompts |

## Data Model (Core)

### Datasets Table

```sql
datasets (
  id            TEXT PRIMARY KEY,   -- portal_id + resource_id
  portal_url    TEXT,               -- CKAN portal base URL
  resource_url  TEXT,               -- direct download/API URL
  title         TEXT,
  schema_shape  TEXT,               -- JSON: column names, types, descriptions
  max_level     INTEGER DEFAULT 0,  -- highest tier completed (0=discovered, 1=schema-vetted, 2=lv1-eda, 3=lv2-eda, ...N)
  cron_levels   TEXT DEFAULT '[]',  -- JSON array: which levels are actively cron'd, e.g. [1,3]
  rejected      BOOLEAN DEFAULT 0,  -- failed a vet at some level
  rejected_at   INTEGER,            -- which level it failed
  reject_reason TEXT,
  created_at    TEXT,
  updated_at    TEXT
)
```

- `max_level` only goes up as analysis deepens
- `cron_levels` is independent — a lv3 dataset can cron [1] for high-freq stats and [3] monthly
- graduated = `len(cron_levels) > 0` (derived, not stored)
- Any cron can be toggled off for cost control

## MVP Scope

### In Scope (P0 only)

1. **Portal registry** — SQLite table of CKAN portal URLs; start with data.gov.sg
2. **Dataset cataloger** — Fetch dataset list + schemas from CKAN API, store in datasets table (level 0)
3. **research-00-schema-vet** — LLM prompt judges schema quality; levels up to 1 or rejects with reason
4. **research-01-lv1-eda-vet** — Python EDA on lv1 survivors; LLM judges results; levels up to 2 or rejects
5. **Artifact system** — Jupyter notebook (or MasterNotebook template) per run per schema per level; decision logs + head/tail samples saved per dataset folder
6. **Chart generation** — Trend charts, histograms, heatmaps for datasets reaching lv2+
7. **SQLite observatory DB** — datasets table with max_level + cron_levels as the game state
8. **Agent roles** — Director, Scout, Vetter, Analyst as distinct prompt personas (characters editable anytime)

### Explicitly Out of Scope (for now)

1. Web UI or dashboard — operator reads SQLite + files directly
2. Cross-dataset joins / Cartographer agent (P1)
3. Advanced EDA / lv2+ tiers (P1)
4. Cron scheduling (P1 — first prove the pipeline works in a single manual run)
5. Publisher agent / town crier (P1 — operator configures separately)
6. Notifications or alerts
7. Multi-portal support beyond data.gov.sg (just append URLs later)

## Monetization

**Model:** None — open research pipeline
**Subscription type:** N/A

Not a SaaS. Value is in published signals, methodology, and the open-sourceable observatory DB.

## User Roles & Permissions

| Role | Can Do | Cannot Do |
|---|---|---|
| operator | Add portals, trigger runs, review decisions, override AI judgments, merge PRs | — |
| ai-agent | Catalog datasets, run vetting, generate artifacts, commit to branches, open PRs | Merge to main, publish without review |
| consumer | Read published outputs, browse observatory DB | Modify data or trigger runs |

## Key Integrations

- **CKAN API** — dataset discovery and metadata fetching
- **Claude API** — LLM judge for schema vetting and EDA interpretation
- **data.gov.sg** — first portal (CKAN-compatible)
- **SQLite3** — observatory database
- **GitHub** — artifact storage (open-research repo), PR-based review flow

## Success Metrics

| Timeframe | Metric | Target |
|---|---|---|
| 30 days | Portal cataloged, schema-vet running on data.gov.sg | 100+ datasets vetted, 10-20 pass to lv1 |
| 60 days | lv1 EDA producing charts for survivors | 5-10 datasets with publication-ready outputs |
| 90 days | Pipeline stable enough to add second portal | 2 portals, cron running on graduated datasets |

## Resolved Design Decisions

### Raw data cache (was gap #2)
Downloaded data lives locally, never committed. Cron cleans up low-level datasets (no reason to keep 200MB CSV for a lv1 reject). High-level datasets keep cache longer.

### lv2+ is a human-AI collaboration loop (was gap #3, open question #1)
lv2+ is NOT full autonomy. It's a loop:
1. AI runs first traverse plan (charts, transforms, feature engineering) — logs everything
2. Human reviews the travelled path, proposes own path, adds metadata and notes for future levels to reference
3. AI runs human's proposed path + new ideas — logs again
4. Loop until path is settled

The notebook is a living document of this collaboration. The gap between AI's first attempt and human's final curation is itself valuable institutional knowledge. AI can log past codes, functions, proposed transforms as context artifacts.

### Cron control (was gap #4)
AI proposes cron_levels. Human personally sets and toggles. Low bandwidth for human, high control over cost.

### Publication (was gap #5)
Start manual — operator reviews outputs, posts what's good. When it becomes predictable, operator writes a cron instruction (could be deterministic script, may not need LLM).

### Joins produce SyntheticTables (was gap #6)

**ProposedJoins table:**
- source_dataset_ids, proposed_by (ai/human), join_key, status (proposed/approved/rejected), reason

**SyntheticTables table (approved joins only):**
- source_dataset_ids, transformation_process (text), notebook_path (clean pipe: raw → transform → join → chart)
- Has own max_level + cron_levels — enters the same game system as regular datasets

### Feedback loop = search function, not prompt stuffing (was gap #7)

The researcher agent gets a search function, not 500 examples in the prompt:
1. What schema am I researching? (columns, types, domain)
2. Find similar past schemas (by column overlap, domain, portal)
3. For each match: level reached, graduation status, rejection reason if any
4. If successfully curated: compare FINAL notebook sequence vs FIRST autonomous attempt
5. The gap between first AI attempt and final human-curated path = institutional knowledge
6. Return top-N most relevant matches as context

## Open Questions

1. **MasterNotebook vs per-schema notebook** — Start with one template adapted per schema, or generate unique notebooks each time? (leaning toward template with per-schema adaptation)
2. **Observatory DB hosting** — Keep SQLite committed in observatory repo, or serve via datasette for web browsing? (start committed, datasette later)
3. **Schema similarity function** — How to match "similar past schemas" for the search function? Column name overlap? Embedding similarity? Domain tags? (can start simple, refine later)
