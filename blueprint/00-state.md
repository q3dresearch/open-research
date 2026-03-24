# Current State (Save File)
<!-- version: 0.6 | phase: 3 | last-updated: 2026-03-25 -->
<!-- ALWAYS READ THIS FILE FIRST IN ANY NEW SESSION -->
<!-- MAX SIZE RULE: This file must NEVER exceed 80 lines. If it does, compress. -->

## Location

| Path | Value |
|---|---|
| Blueprint | `open-research/blueprint/` |
| Project repo | `q3dresearch/open-research` (public) |
| Observatory DB | `observatory.db` (SQLite, committed to repo) |
| Skills | `q3d/skills/` (local) |

## HUD

| Field | Value |
|---|---|
| Phase | Gate 3 passed → ready to build (M0: Scaffold) |
| Milestone | M0: Project Scaffold |
| Current task | Create Python project structure, lib/db.py, lib/llm.py, tests |
| Done when | Smoke tests pass, DB initializes correctly |
| Blocked by | nothing — ready to build |
| Last save | `saves/gate-3-plan-approved.md` |

## What's Next

1. Build M0: scaffold (lib/db.py, lib/llm.py, requirements.txt, tests, CLAUDE.md)
2. Build M1: scout (lib/ckan.py, agents/scout.py) → discover data.gov.sg
3. Build M2: vetter (prompts/research-00, agents/vetter.py) → schema judgment
4. Build M3: analyst (lib/eda.py, lib/cache.py, notebooks) → EDA
5. Build M4: charts + director → LAUNCH

## Scope Queue

- [2026-03-24] "cross-dataset joins" — P1 (M7)
- [2026-03-24] "cron for graduated datasets" — P1 (M6)
- [2026-03-24] "lv2 advanced EDA tier" — P1 (M5)
- [2026-03-24] "publisher agent" — P1 (M8)

## Handoff (for next AI)

FULL BLUEPRINT COMPLETE. All phases done (1→2→3). Read 03-milestones.md for build plan. 5 milestones to LAUNCH: M0(scaffold) → M1(scout) → M2(vetter) → M3(analyst) → M4(charts+director). Start building M0. Generate CLAUDE.md from 03-claude-md.md. This is a Python CLI pipeline, NOT a web app.
