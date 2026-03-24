# Gate 1 Snapshot — PRD & Idea Extraction
<!-- saved: 2026-03-25 -->

## Status
Phase 1 Q&A complete. PRD filled. All 7 design gaps identified and resolved.
3 open questions remain (low severity, safe to resolve in Phase 2).

## Files at this gate
- `00-variables.md` — fully populated with game model, agent roles, level system, all resolved decisions
- `01-prd.md` — filled PRD with data model, user stories, MVP scope, resolved design decisions

## Key decisions locked
1. Level system: max_level (int) + cron_levels (array) — independent axes
2. lv2+ is human-AI collaboration loop, not full autonomy
3. AI proposes cron, human toggles
4. Publisher is manual first, cron later
5. Joins → ProposedJoins + SyntheticTables (same level system)
6. Feedback = schema similarity search, not prompt stuffing (embeddings → flat numpy → sqlite-vec)
7. Research library (eda.py) + thin notebooks, not monolithic notebooks
8. SQLite committed, scale to hosted DB if >50MB
9. Raw data cached locally, never committed, cron cleans low-level

## What's next
- Phase 2: Architecture (file tree, full SQLite schema, prompt templates, agent wiring, risk registry, test strategy)
- To resume: `/neldivad-blueprint-instantiator resume open-research`
