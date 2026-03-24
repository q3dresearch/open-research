# Stack Decisions
<!-- version: 0.1 | phase: 2 | last-updated: 2026-03-25 -->

## System Overview

open-research allows an operator to add CKAN portal URLs and have an AI autonomously discover, vet, and analyze public datasets through graduated tiers, producing publication-ready charts and recurring signals.

This is NOT a web app. It's a **Python CLI/agent pipeline** that writes artifacts to disk and tracks state in SQLite.

## Core Stack

### Language: Python 3.11+
- **Why:** Data science ecosystem (pandas, matplotlib, seaborn, scipy). Jupyter notebook generation. Claude API SDK.
- **Rejected:** Node.js (poor data science libs), R (poor general-purpose scripting, harder to integrate with Claude API).

### Framework: Python scripts + Claude Code agents
- **Why:** No web framework needed. Agents are Python scripts invoked by Claude Code or cron. Each agent (scout, vetter, analyst, etc.) is a standalone script.
- **Rejected:** FastAPI/Flask (no web server needed for MVP), Airflow/Prefect (overkill orchestration for a solo operator).

### Notebook Runtime: Jupyter (nbformat + papermill)
- **Why:** Notebooks are the artifact of record. `papermill` allows parameterized execution (pass dataset_id, level). `nbformat` allows programmatic notebook generation from templates.
- **Rejected:** Plain Python scripts (lose the visual audit trail — charts inline with code and commentary).

## Infrastructure

### Database: SQLite3
- **Why:** Single file, portable, zero-config, committable to git, browseable with any SQL tool. The observatory DB IS the product — it's the game state.
- **Rejected:** PostgreSQL (needs a server, overkill for <100k rows), DuckDB (better for analytics but less tooling for CRUD ops, less ecosystem support for committed DB files).
- **Scaling path:** If SQLite file exceeds ~50MB or needs concurrent writers, migrate to Turso (SQLite-compatible edge DB) or Neon (Postgres).

### Hosting: Local machine + GitHub
- **Why:** Compute runs locally (or on any machine with Python + Claude API key). Artifacts committed to GitHub for persistence and sharing.
- **Rejected:** Cloud functions (cold starts, complexity for batch jobs), dedicated server (unnecessary cost for solo operator).

### File Storage: Git repo (artifacts) + local cache (raw data)
- **Why:** Notebooks, charts, decision logs, and the SQLite DB are committed. Raw downloaded CSVs are gitignored and cached locally with a cleanup cron for low-level rejects.
- **Rejected:** S3/GCS (cost and complexity for what's essentially <1GB of artifacts).

## Services

### LLM: Claude API (Anthropic)
- **Why:** Used as the judge at every vetting gate. Also used for generating schema embeddings for similarity search. The entire pipeline is built around Claude as the reasoning engine.
- **Cost model:** ~$0.003-0.01 per schema vet (small prompt), ~$0.01-0.05 per EDA vet (larger context with stats), ~$0.05-0.20 per lv2 analysis. Budget: ~$5-20/month for MVP scale.
- **Rejected:** OpenAI (Claude is the native choice for Claude Code agents), local LLMs (insufficient reasoning quality for data science judgment).

### CKAN API: Direct HTTP
- **Why:** CKAN has a standard REST API. No SDK needed — just `requests` or `httpx` with rate limiting.

### Auth: N/A
- **No web app.** Access control = GitHub repo permissions + Claude API key in env.

### Payments: N/A
### Email: N/A
### UI: N/A

## API Style: CLI / Agent scripts
- **Why:** Each agent is a Python script invoked with arguments: `python agents/scout.py --portal data.gov.sg`. No HTTP API needed. Operator interacts via CLI, SQLite queries, and file inspection.

## Cost Estimate (Monthly)

| Service | Provider | Free Tier? | Est. Cost at MVP | Est. Cost at Scale (10 portals) |
|---|---|---|---|---|
| LLM | Claude API | $5 free credits | $5-20/mo | $50-100/mo |
| Compute | Local machine | Yes | $0 | $0 |
| Storage | GitHub | Yes (public repo) | $0 | $0 |
| Database | SQLite (local file) | Yes | $0 | $0 (until migration) |
| **Total** | | | **$5-20/mo** | **$50-100/mo** |

## Package List

### Dependencies
```
# Core
python>=3.11
pandas>=2.0
numpy>=1.24

# Notebooks
jupyter>=1.0
papermill>=2.4
nbformat>=5.9

# Charts
matplotlib>=3.7
seaborn>=0.12

# LLM
anthropic>=0.40

# HTTP
httpx>=0.25
tenacity>=8.2          # retry with backoff for CKAN API

# Database
# (sqlite3 is stdlib — no package needed)

# Embeddings (P1)
# scikit-learn>=1.3    # cosine_similarity for flat numpy search
```

### Dev Dependencies
```
# Testing
pytest>=7.4
pytest-asyncio>=0.21

# Linting
ruff>=0.1

# Types
mypy>=1.5
```
