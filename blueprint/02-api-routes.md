# API Routes
<!-- version: 0.1 | phase: 2 | last-updated: 2026-03-25 -->

## N/A — No HTTP API

This project is CLI-driven. Agents are invoked as Python scripts, not HTTP endpoints.

## Agent CLI Interface

### Scout
```bash
python agents/scout.py --portal <portal_id>
# Crawls CKAN catalog, inserts level-0 rows into datasets table
# Options:
#   --portal    Portal ID from portals table (required)
#   --limit N   Max datasets to discover per run (default: all)
#   --dry-run   Print what would be discovered without writing to DB
```

### Vetter
```bash
python agents/vetter.py --dataset <dataset_id>
python agents/vetter.py --portal <portal_id> --level <N>
# Runs research-NN prompt on dataset(s), levels up or rejects
# Options:
#   --dataset   Single dataset ID to vet (mutually exclusive with --portal)
#   --portal    Batch vet all datasets at --level for this portal
#   --level     Which level to vet at (default: next level for the dataset)
#   --dry-run   Print prompt and mock verdict without calling Claude
```

### Analyst
```bash
python agents/analyst.py --dataset <dataset_id> --level <N>
# Runs EDA notebook for a dataset at a given level
# Options:
#   --dataset   Dataset ID (required)
#   --level     Which EDA tier to run (required)
#   --rerun     Force rerun even if level already completed
```

### Director
```bash
python agents/director.py
# Reads game state, outputs a prioritized task list
# Options:
#   --execute   Actually dispatch the top-priority task (default: just print plan)
#   --budget    Override daily budget cap (default: from portals.yaml)
```

### Cartographer (P1)
```bash
python agents/cartographer.py --portal <portal_id>
# Proposes joins between high-level datasets in a portal
# Options:
#   --portal    Scope to one portal (default: all)
#   --min-level Minimum max_level for datasets to consider (default: 2)
```

### Publisher (P1)
```bash
python agents/publisher.py --dataset <dataset_id>
python agents/publisher.py --all-graduated
# Generates publication-ready charts for graduated datasets
# Options:
#   --dataset       Single dataset
#   --all-graduated All datasets with non-empty cron_levels
#   --format        Output format: png, svg (default: png)
```

## Common Patterns

All agents follow the same structure:
1. Parse CLI args
2. Connect to `observatory.db`
3. Read relevant state
4. Do work (API calls, notebook execution, LLM calls)
5. Write results to DB (runs table) and disk (artifacts/)
6. Exit with status code (0 = success, 1 = failure, 2 = skipped)

Error output goes to stderr. Structured output (JSON) goes to stdout for piping.
