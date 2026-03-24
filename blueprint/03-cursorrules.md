# .cursorrules / AI Rules Generator
<!-- version: 0.1 | phase: 3 | last-updated: 2026-03-25 -->

## Generated Rules Content

These rules apply to any AI coding agent working on this project (Claude Code, Cursor, etc.)

```
# open-research — AI Agent Rules

## Project Context
Project: open-research
Description: Autonomous AI research pipeline over public datasets (CKAN portals)
Primary entity: Dataset (a table/resource from a public portal)
This is NOT a web app. It is a Python CLI/agent pipeline.

## Stack
- Language: Python 3.11+
- Database: SQLite3 (observatory.db) — raw SQL via lib/db.py
- LLM: Claude API via lib/llm.py
- Notebooks: Jupyter via papermill
- Charts: matplotlib + seaborn
- HTTP: httpx + tenacity

## Architecture Rules
- All database access goes through lib/db.py — never raw sqlite3 calls in agents
- All LLM calls go through lib/llm.py — never direct anthropic SDK calls in agents
- All EDA functions live in lib/eda.py — notebooks import the library
- Agents are thin orchestrators: read state → call lib functions → write state
- Every agent run creates a row in the runs table — no silent execution
- Notebooks stay thin: import lib, call functions, render results. Logic lives in lib/

## File Conventions
- Library modules: lib/{purpose}.py (snake_case)
- Agent scripts: agents/{role}.py (snake_case)
- Prompt templates: prompts/{name}.md (kebab-case)
- Notebook templates: templates/{name}.ipynb
- Artifacts: artifacts/{dataset_id}/{type}/{run_id}-{name}.{ext}
- Tests: tests/test_{module}.py

## Coding Standards
- Python 3.11+ features OK (match/case, tomllib, etc.)
- Type hints on all public functions
- Docstrings on all public functions (Google style)
- Use pathlib.Path for file paths, not string concatenation
- Use httpx (not requests) for HTTP calls
- Use tenacity for retry logic
- JSON fields in SQLite stored as TEXT — serialize/deserialize in lib/db.py

## Naming
- Files: snake_case.py
- Functions: snake_case
- Classes: PascalCase
- Constants: UPPER_SNAKE_CASE
- Database columns: snake_case
- Env vars: UPPER_SNAKE_CASE

## Do NOT
- Do not commit raw data files (data/ is gitignored)
- Do not hardcode API keys — use .env
- Do not add pip packages without checking 02-stack.md requirements.txt
- Do not modify SQLite schema without updating 02-schema.md first
- Do not add new agents without updating 02-file-tree.md and 02-api-routes.md
- Do not skip the runs table — every execution must be logged
- Do not put business logic in notebooks — it belongs in lib/
- Do not use pandas for simple operations where sqlite queries suffice
- Do not add features not listed in 01-prd.md or 03-milestones.md

## When You're Stuck
- Read the relevant 02-*.md blueprint file for the architecture spec
- Check 02-risk-registry.md for known pitfalls
- Follow the Self-Diagnostic Protocol in 02-test-strategy.md
- Don't guess — add logging, read the output, fix the specific failure
```
