# Gate 2 Snapshot — Architecture
<!-- saved: 2026-03-25 -->

## Status
Phase 2 complete. All 02-*.md architecture docs filled. Sync check passed.

## Files at this gate

| File | Status | Key content |
|---|---|---|
| 02-stack.md | Filled | Python 3.11+, SQLite, Claude API, papermill, ~$5-20/mo |
| 02-schema.md | Filled | 6 tables: portals, datasets, runs, proposed_joins, synthetic_tables, schema_embeddings |
| 02-file-tree.md | Filled | 36 files (27 MVP): lib/, agents/, prompts/, templates/, artifacts/, tests/ |
| 02-risk-registry.md | Filled | 28 risks across 7 categories |
| 02-test-strategy.md | Filled | 4 test levels: smoke, unit, integration, live |
| 02-api-routes.md | Filled | CLI interface for all 6 agents |
| 02-auth-flow.md | N/A | No web app |
| 02-payment-flow.md | N/A | No monetization (internal cost tracking only) |
| 02-pages-and-components.md | N/A | No web UI (CLI + SQLite browser + file inspection) |

## Key architecture decisions
- SQLite is THE game state — observatory.db committed to git
- 6 agent scripts: director, scout, vetter, analyst, cartographer (P1), publisher (P1)
- Research library (lib/) with composable functions — notebooks stay thin
- Prompt templates in prompts/ dir — versioned, auditable
- Artifacts per dataset per run: notebooks, charts, decision logs
- Raw data cached locally (gitignored), cleaned up by cron for low-level rejects
- Costs tracked per-run, daily budget cap enforced by Director

## What's next
- Phase 2.5: discover relevant skills via find-skills
- Phase 3: milestones, build plan, CLAUDE.md + cursorrules generation
