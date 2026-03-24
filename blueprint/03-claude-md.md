# CLAUDE.md Generator
<!-- version: 0.1 | phase: 3 | last-updated: 2026-03-25 -->

## Generated CLAUDE.md Content

Place this at: `open-research/CLAUDE.md` (replacing the existing one during M0)

```markdown
# open-research

AI agent that autonomously discovers, vets, and analyzes public datasets from CKAN portals,
producing publication-ready charts and recurring alerts when indicators move.

## What Is This

An autonomous research pipeline. NOT a web app. The operator adds a CKAN portal URL,
and AI agents crawl, vet, and analyze datasets through graduated tiers.

The **observatory.db** SQLite file IS the game state. The `datasets.max_level` column
tracks how deeply each dataset has been analyzed. The `datasets.cron_levels` array
tracks which levels are actively producing output.

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Database | SQLite3 (observatory.db, committed to repo) |
| LLM | Claude API (Anthropic) |
| Notebooks | Jupyter via papermill |
| Charts | matplotlib + seaborn |
| HTTP | httpx + tenacity |

## Project Structure

```
lib/            Research library (eda.py, ckan.py, charts.py, db.py, llm.py, etc.)
agents/         Agent scripts (director.py, scout.py, vetter.py, analyst.py)
prompts/        LLM judge prompt templates (research-00-schema-vet.md, etc.)
templates/      Jupyter notebook templates (lv1-eda-template.ipynb)
artifacts/      Generated outputs per dataset (notebooks, charts, decision logs)
data/           [GITIGNORED] Raw downloaded data cache
tests/          pytest test suite
```

## Commands

```bash
# Agents
python agents/scout.py --portal data-gov-sg     # Discover datasets
python agents/vetter.py --portal data-gov-sg --level 0  # Vet schemas
python agents/analyst.py --dataset <id> --level 1       # Run EDA
python agents/director.py                        # Get daily priorities
python agents/director.py --execute              # Auto-dispatch top task

# Tests
pytest tests/ -m smoke       # Quick sanity check
pytest tests/ -m unit        # Unit tests
pytest tests/ -m integration # Integration tests
pytest tests/ -m live --live # Hit real APIs (costs money)
```

## Database Tables

| Table | Purpose |
|---|---|
| portals | Registry of CKAN portal URLs |
| datasets | THE GAME STATE — every dataset with max_level + cron_levels |
| runs | Every pipeline execution (the quest log) |
| proposed_joins | Cross-dataset join proposals |
| synthetic_tables | Approved joins that became new research entities |
| schema_embeddings | Cached vectors for similarity search |

## Agent Roles

| Agent | Job |
|---|---|
| Director | Decides daily priorities, dispatches others |
| Scout | Crawls portals, fills level-0 rows |
| Vetter | Runs research-NN prompts, levels up or rejects |
| Analyst | Runs EDA notebooks, produces artifacts |
| Cartographer | Proposes cross-dataset joins (P1) |
| Publisher | Generates publication-ready outputs (P1) |

## Blueprint Files

Architecture decisions live in `blueprint/`. If you need to change the architecture,
update the blueprint doc FIRST, then change the code.

| File | Purpose |
|---|---|
| 01-prd.md | What we're building and why |
| 02-stack.md | Technology choices with justification |
| 02-schema.md | SQLite schema (source of truth for lib/db.py) |
| 02-file-tree.md | Complete file structure |
| 02-risk-registry.md | Known risks and mitigations |
| 02-test-strategy.md | How to test |
| 03-milestones.md | Build plan and progress |

## Rules

- Never commit raw data (data/ is gitignored)
- Never hardcode API keys — use .env
- Every agent run logs to the runs table — no silent runs
- Notebooks are the artifact of record — never delete them
- Prompts are versioned in prompts/ — log which version was used per run
- Human reviews all verdicts before promoting datasets to cron
- If you need to change a table schema, update 02-schema.md first

## Environment Variables

```env
ANTHROPIC_API_KEY=     # Claude API key
```

## Current Milestone

See `blueprint/03-milestones.md` and `blueprint/00-state.md`.
```
