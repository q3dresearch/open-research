---
title: Pipeline Types
description: How datasets are classified by the type of analysis they support
---

# Pipeline Types

The q3d pipeline is framed as a **research story** — each dataset produces a narrative with characters, structure, and a conclusion. Different types of datasets support different types of stories.

## The Story Metaphor

Think of each pipeline run as producing a **visual novel** from a dataset:

- The **rows** are the characters — more of them means a richer, more complex story.
- The **phases** are the plot — EDA sets the scene, cleaning resolves inconsistencies, engineering develops the characters, clustering discovers factions, and the report delivers the ending.
- The **human notes** are the author's intent — what the story is about, what matters.

Not every dataset can support the same kind of story. A dataset of 24 aggregate statistics can't develop individual characters. A time-series of monthly readings can't explore individual-level behavior. Each type of dataset calls for a different narrative form.

---

## Types

### `transactional` — The Full Story

Row-level data where each record is one event, transaction, or entity observation.

**Characteristics:**
- Thousands to millions of rows
- Each row represents one unit (a sale, a person, an incident, a measurement at one location)
- Has a natural target variable (price, outcome, count)
- Contains variation across rows that can be modeled

**Pipeline:** Full 7-phase pipeline — vet → eda → clean → engineer → cluster → select → report

**Examples:**
- HDB resale flat transactions (`resale_price` per flat per month)
- Individual taxi trips
- Individual inspection records

---

### `aggregate` — The Backdrop

Pre-grouped summary statistics or pivot tables where rows represent groups, not individuals.

**Characteristics:**
- Few rows (often under 500) — one row per category, bracket, or time bucket
- Values are counts, means, totals, rates — not individual observations
- High join potential: provides population context when merged with transactional data
- Low standalone modeling value — but enriches other datasets

**Pipeline:** Lightweight analysis — schema vet → EDA summary → join proposal. No feature engineering or modeling alone. Designed for cross-dataset enrichment.

**Examples:**
- Household income distribution by language (24 rows, one per income bracket × language group)
- Unemployment rate by quarter (136 rows, one per quarter × demographic group)
- Monthly average rainfall by station (one row per month per station)

**Join value:** An `aggregate` dataset describing income distribution by neighborhood can enrich a `transactional` flat-price dataset, adding population-level context to individual sale records.

---

### `reference` — The Atlas

Pure lookup/classification tables with no time dimension and no analytical variation — just canonical mappings.

**Characteristics:**
- Static or slowly-changing
- Maps codes to descriptions, geographic areas to regions, etc.
- No modeling potential on its own — pure enrichment

**Pipeline:** Ingested and stored, available for join proposals. No analysis run.

**Examples:**
- Postal code → town → planning area mapping
- Flat type → bedroom count codes
- HDB block → GPS coordinates

---

## Classification

The vetter classifies each dataset at phase 00 and records the `pipeline_type` in the database. The rest of the pipeline routes accordingly:

| pipeline_type | Vetter verdict | Phases run |
|---------------|---------------|------------|
| `transactional` | pass | 00 → 10 → 15 → 20 → 25 → 30 → 50 |
| `aggregate` | pass (aggregate) | 00 → EDA summary → join proposal |
| `reference` | pass (reference) | Ingested, available for joins only |

An `aggregate` dataset that is rejected outright (poor quality, no join potential) receives `verdict: fail` like any other.

---

## Join Proposals

When a `transactional` dataset and an `aggregate` dataset share a natural join key, the system creates a `proposed_join` record in the database. A human can approve or reject the join. Approved joins create `synthetic_tables` — new enriched datasets that run the full `transactional` pipeline on the joined data.

This is how the system scales: standalone `transactional` stories, supplemented by `aggregate` backdrops that add population-level context.
