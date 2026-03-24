# Milestones
<!-- version: 0.1 | phase: 3 | last-updated: 2026-03-25 -->

## Milestone Route Map

```
M0: Scaffold ──► M1: Scout ──► M2: Vetter ──► M3: Analyst ──► M4: Charts ──► LAUNCH
   (tutorial)     (discover)    (judge)        (research)      (produce)        │
                                                                                 │
                                                                    ┌────────────┘
                                                                    ▼
                                                               NEW GAME+
                                                               M5: lv2 EDA
                                                               M6: Cron
                                                               M7: Joins
                                                               M8: Publisher
```

---

## M0: Project Scaffold (Tutorial Zone)

**Dependencies:** All Phase 2 documents approved
**Implements:** 02-file-tree.md, 02-stack.md, 02-schema.md

| Task | Status | Notes |
|---|---|---|
| Create Python project structure (lib/, agents/, prompts/, templates/, artifacts/, tests/) | | |
| Write `requirements.txt` from 02-stack.md | | |
| Implement `lib/db.py` — SQLite init, create all tables from 02-schema.md | | |
| Create `observatory.db` with seed data (data.gov.sg portal row) | | |
| Write `portals.yaml` with first portal entry | | |
| Create `.env.example` with `ANTHROPIC_API_KEY` placeholder | | |
| Update `.gitignore` (data/, *.pyc, .env, __pycache__) | | |
| Implement `lib/llm.py` — Claude API wrapper, prompt rendering, cost estimation | | |
| Set up pytest with conftest.py fixtures (temp DB, mock responses) | | |
| Write smoke tests: DB init, table creation, LLM mock response parsing | | |
| Generate CLAUDE.md from 03-claude-md.md | | |
| Verify: `pytest tests/ -m smoke` passes | | |

**Done when:** Project runs locally, SQLite DB initializes with correct schema, smoke tests pass, `lib/db.py` and `lib/llm.py` work.

**Review Gate:** Verify file tree matches 02-file-tree.md. Run smoke tests.

---

## M1: Scout — Portal Discovery (Unlock the Map)

**Dependencies:** M0 complete
**Implements:** lib/ckan.py, agents/scout.py

| Task | Status | Notes |
|---|---|---|
| Implement `lib/ckan.py` — list_datasets, get_resource_schema, parse CKAN API response | | |
| Implement `agents/scout.py` — crawl portal, insert level-0 rows into datasets table | | |
| Handle CKAN API pagination (some portals have 1000+ datasets) | | |
| Rate limiting + retry with backoff (tenacity) | | |
| Log run in runs table: agent=scout, status, metrics (datasets discovered) | | |
| Unit tests: parse mock CKAN catalog, mock resource metadata | | |
| Integration test: scout.py with mock CKAN → correct rows in DB | | |
| Live test: scout data.gov.sg, verify ≥100 datasets at level 0 | | |

**Done when:** `python agents/scout.py --portal data-gov-sg` populates datasets table with real data.gov.sg schemas.

**Review Gate:** Show the datasets table. Spot-check 10 rows for schema quality. Verify idempotent on re-run.

---

## M2: Vetter — Schema Judgment (First Boss)

**Dependencies:** M1 complete (need level-0 rows to vet)
**Implements:** prompts/research-00-schema-vet.md, agents/vetter.py

| Task | Status | Notes |
|---|---|---|
| Write `prompts/research-00-schema-vet.md` — prompt template for schema judgment | | |
| Implement prompt variable substitution in `lib/llm.py` (load .md, inject schema, send) | | |
| Define structured output format: `{verdict, score, reason, suggested_level}` | | |
| Implement `agents/vetter.py` — load prompt, call Claude, parse verdict, update dataset level | | |
| On pass: set max_level = 1. On reject: set rejected = 1, rejected_at_level = 0, reject_reason | | |
| Log full run: prompt sent, response received, verdict, cost | | |
| Save decision log artifact: `artifacts/{dataset_id}/logs/{run_id}-decision.json` | | |
| Unit tests: verdict parsing (pass, reject, malformed) | | |
| Integration test: vetter.py with mock Claude → correct DB state transitions | | |
| Live test: vet 20 level-0 datasets, review verdicts for quality | | |

**Done when:** `python agents/vetter.py --portal data-gov-sg --level 0` processes all level-0 datasets with logged verdicts.

**Review Gate:** Read 10 pass and 10 reject verdicts. This gate determines prompt quality. Tune `research-00-schema-vet.md` until verdicts match human judgment.

---

## M3: Analyst — Basic EDA (Main Quest)

**Dependencies:** M2 complete (need level-1 rows)
**Implements:** lib/eda.py, lib/cache.py, lib/notebooks.py, templates/lv1-eda-template.ipynb, prompts/research-01-lv1-eda-vet.md

| Task | Status | Notes |
|---|---|---|
| Implement `lib/cache.py` — download resource, check Content-Length, encoding fallback, store in data/ | | |
| Implement `lib/eda.py` — getMissingValues, getMinMax, getMedian, getStd, getCardinality, getSample, getDistributions | | |
| Create `templates/lv1-eda-template.ipynb` — imports lib, runs EDA functions, renders inline | | |
| Implement `lib/notebooks.py` — load template, parameterize, execute via papermill, save to artifacts/ | | |
| Write `prompts/research-01-lv1-eda-vet.md` — input: schema + EDA stats → "is there signal?" | | |
| Implement `agents/analyst.py` — download data, run notebook, send EDA to Claude, parse verdict | | |
| On pass: set max_level = 2. On reject: set rejected = 1, rejected_at_level = 1 | | |
| Save artifacts: executed notebook + decision log with head/tail samples | | |
| Unit tests: EDA functions on clean/missing/empty data | | |
| Integration test: analyst.py with mock data + mock Claude → notebook + artifacts | | |
| Live test: run lv1 EDA on 5 level-1 datasets | | |

**Done when:** `python agents/analyst.py --dataset <id> --level 1` downloads data, generates notebook, gets verdict, saves everything.

**Review Gate:** Open 3 generated notebooks in Jupyter. Check: are EDA results informative? Are LLM verdicts sensible? Is the decision log sufficient for future context?

---

## M4: Charts + Director (Launch Prep)

**Dependencies:** M3 complete (need level-2 rows with EDA results)
**Implements:** lib/charts.py, agents/director.py, prompts/director-daily.md

| Task | Status | Notes |
|---|---|---|
| Implement `lib/charts.py` — generate_trend, generate_histogram, generate_heatmap | | |
| Add branding: color palette, source attribution, date range, q3d watermark | | |
| Integrate chart generation into analyst.py — on lv1 pass, generate charts for key columns | | |
| Save charts to `artifacts/{dataset_id}/charts/` as PNG | | |
| Write `prompts/director-daily.md` — given game state summary, output prioritized task list | | |
| Implement `agents/director.py` — query DB, summarize game state, ask Claude for priorities | | |
| Add `--execute` flag: auto-dispatch top-priority task | | |
| Implement cache cleanup in `lib/cache.py` — delete raw data for rejected datasets | | |
| Full pipeline test: scout → vet(lv0) → analyst(lv1) → charts for one dataset end-to-end | | |

**Done when:** Pipeline works end-to-end for data.gov.sg. Director recommends daily actions. Charts exist for survivors.

**Review Gate:** Run `python agents/director.py` — is its task prioritization sensible? Browse `artifacts/` — are charts publication-quality? Can you trust this system to run semi-autonomously?

---

## Campaign Complete

**Win condition:** Pipeline works end-to-end on data.gov.sg.

| Task | Status |
|---|---|
| data.gov.sg fully scouted (all datasets at level 0+) | |
| Schema-vet prompt produces reasonable verdicts | |
| lv1 EDA notebooks are informative and well-formatted | |
| Charts have branding, attribution, correct data | |
| Director produces sensible priorities | |
| All artifacts organized in `artifacts/{dataset_id}/` | |
| observatory.db is browseable and makes sense | |
| `00-state.md` → Phase: SHIPPED | |
| Save: `saves/gate-4-shipped.md` | |
| Push everything to `q3dresearch/open-research` | |

---

## New Game+ (Post-Launch Backlog)

### Backlog

| Request | Date | Priority |
|---|---|---|
| lv2 advanced EDA (human-AI collaboration loop) | 2026-03-24 | ship-next |
| Cron scheduling for graduated datasets | 2026-03-24 | ship-next |
| Cross-dataset joins (Cartographer) | 2026-03-24 | ship-next |
| Publisher agent (town crier) | 2026-03-24 | ship-next |
| Schema similarity search (embeddings) | 2026-03-24 | ship-later |
| Multi-portal support (openAFRICA, AU, CA) | 2026-03-24 | ship-later |
| Web UI / Datasette | 2026-03-24 | ship-later |

### M5: lv2 Advanced EDA

| Task | Status | Notes |
|---|---|---|
| Implement `lib/transforms.py` | | |
| Create `templates/lv2-eda-template.ipynb` | | |
| Write `prompts/research-02-lv2-eda-vet.md` | | |
| Human notes workflow: operator writes `artifacts/{id}/human/notes.md`, analyst reads | | |
| Log full traverse path: code tried, transforms proposed, results | | |

### M6: Cron Scheduling

| Task | Status | Notes |
|---|---|---|
| cron_levels management in `lib/db.py` | | |
| Director proposes, operator toggles | | |
| Cron runner: re-run notebooks at matching frequency | | |
| Skip if CKAN `last_modified` unchanged | | |
| Daily budget enforcement | | |

### M7: Cartographer + Joins

| Task | Status | Notes |
|---|---|---|
| Write `prompts/cartographer-join-proposal.md` | | |
| Implement `agents/cartographer.py` | | |
| Operator review workflow for proposed_joins | | |
| Approved → synthetic_tables, enter level system | | |
| Create `templates/join-template.ipynb` | | |

### M8: Publisher (Town Crier)

| Task | Status | Notes |
|---|---|---|
| Implement `agents/publisher.py` | | |
| Branding templates (watermark, palette, typography) | | |
| LLM narrative: 2-4 bullet insights per chart | | |
| Manual first, scriptable cron later | | |

---

## Milestone Status Tracker

| Milestone | Status | Started | Completed | Learnings |
|---|---|---|---|---|
| M0: Scaffold | not started | | | |
| M1: Scout | not started | | | |
| M2: Vetter | not started | | | |
| M3: Analyst | not started | | | |
| M4: Charts + Director | not started | | | |
| — LAUNCH — | | | | |
| M5: lv2 EDA | not started | | | |
| M6: Cron | not started | | | |
| M7: Joins | not started | | | |
| M8: Publisher | not started | | | |
