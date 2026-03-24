# q3d Open Research — Claude Context

## What this repo is

Published research outputs for q3d research's observatories.
This is the **public-facing** output layer. Do not commit raw data dumps or private infra configs here.

## Key directories

- `datasets/` — one `dataset.yaml` per adopted dataset (archetype, field mappings, tier, source)
- `signals/` — one `signals.yaml` per signal template, referencing input datasets
- `runs/` — one `run.yaml` per pipeline execution (provenance, step statuses, artifact paths)
- `outputs/` — generated charts, narrative drafts, EDA reports

## Skills loaded here

- `open-data-observatory-v1` — executes ingest → EDA → signals → publish
- `research-director` — orchestrates: tiers datasets, plans pipelines, delegates to observatory

Skills are defined in `../skills/` (local) or via `skills-lock.json`.

## Workflow

1. Add a new dataset config to `datasets/` with archetype + field mappings
2. Run the research-director to tier it and plan the pipeline
3. Run open-data-observatory-v1 to ingest, compute signals, generate outputs
4. Review outputs in `outputs/drafts/` before publishing
5. Every run emits a `runs/run-{id}.yaml` — never skip this

## Rules

- Never present speculative signals as facts
- Always include source attribution and data access date
- Keep a human in the loop for publication decisions
- Respect dataset licenses — check before republishing raw data
