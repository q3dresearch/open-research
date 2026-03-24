# File Tree
<!-- version: 0.1 | phase: 2 | last-updated: 2026-03-25 -->

## Project Root

```
open-research/
├── .gitignore                              # [MVP] Ignore data/, *.pyc, .env
├── CLAUDE.md                               # [MVP] AI context for Claude Code sessions
├── requirements.txt                        # [MVP] Python dependencies
├── observatory.db                          # [MVP] SQLite database — the game state
├── portals.yaml                            # [MVP] List of CKAN portal URLs to crawl
├── skills-lock.json                        # [MVP] Skill references (local + remote)
│
├── blueprint/                              # [EXISTS] Phase docs from instantiator
│   ├── 00-state.md                         # Current state / save file
│   ├── 00-variables.md                     # Variable registry
│   ├── 01-prd.md                           # Product requirements
│   ├── 02-*.md                             # Architecture docs
│   └── saves/                              # Gate snapshots
│
├── lib/                                    # [MVP] Research library — composable functions
│   ├── __init__.py                         # Package init
│   ├── db.py                               # [MVP] SQLite helpers: connect, query, upsert, migrate
│   ├── ckan.py                             # [MVP] CKAN API client: list datasets, fetch schema, download resource
│   ├── eda.py                              # [MVP] Basic EDA: getMissingValues, getMinMax, getSample, getCardinality, getDistributions
│   ├── transforms.py                       # [P1]  Feature engineering: panel conversion, group deltas, time decomposition
│   ├── charts.py                           # [MVP] Chart generation: trend lines, histograms, heatmaps, branded output
│   ├── notebooks.py                        # [MVP] Notebook helpers: create from template, inject cells, execute via papermill
│   ├── llm.py                              # [MVP] Claude API wrapper: send prompt, parse structured response, log cost
│   ├── embeddings.py                       # [P1]  Schema similarity: embed text, cosine search, find similar schemas
│   └── cache.py                            # [MVP] Raw data cache: download, store, cleanup cron for low-level rejects
│
├── prompts/                                # [MVP] LLM judge prompt templates (markdown)
│   ├── research-00-schema-vet.md           # [MVP] Input: schema shape, col descriptions, title → "worth downloading?"
│   ├── research-01-lv1-eda-vet.md          # [MVP] Input: above + EDA stats → "is there signal?"
│   ├── research-02-lv2-eda-vet.md          # [P1]  Input: above + transforms → "is this publishable?"
│   ├── director-daily.md                   # [MVP] Director prompt: given game state, what should we work on today?
│   └── cartographer-join-proposal.md       # [P1]  Input: two+ schemas → "should these be joined?"
│
├── agents/                                 # [MVP] Agent entry points — one script per character
│   ├── director.py                         # [MVP] Reads game state, decides daily priorities, dispatches agents
│   ├── scout.py                            # [MVP] Crawls a portal, fills datasets table with level-0 rows
│   ├── vetter.py                           # [MVP] Runs research-NN prompt on a dataset, levels up or rejects
│   ├── analyst.py                          # [MVP] Runs EDA notebook for a dataset at a given level
│   ├── cartographer.py                     # [P1]  Proposes cross-dataset joins
│   └── publisher.py                        # [P1]  Generates publication-ready outputs for graduated datasets
│
├── templates/                              # [MVP] Notebook templates
│   ├── lv1-eda-template.ipynb              # [MVP] MasterNotebook for level-1 basic EDA
│   ├── lv2-eda-template.ipynb              # [P1]  MasterNotebook for level-2 advanced EDA
│   └── join-template.ipynb                 # [P1]  MasterNotebook for synthetic table creation
│
├── artifacts/                              # [MVP] Generated outputs, committed to git
│   └── {dataset_id}/                       # One folder per dataset
│       ├── notebooks/                      # Executed notebooks per run per level
│       │   └── {run_id}-lv{N}.ipynb
│       ├── charts/                         # PNG/SVG chart outputs
│       │   └── {run_id}-{chart_name}.png
│       ├── logs/                           # Decision logs
│       │   └── {run_id}-decision.json      # LLM prompt, response, verdict, head/tail samples
│       └── human/                          # Operator's notes, overrides, steering
│           └── notes.md
│
├── data/                                   # [GITIGNORED] Raw downloaded data cache
│   └── {dataset_id}/
│       └── raw.{csv|json|xlsx}
│
└── tests/                                  # [MVP] Test suite
    ├── conftest.py                         # Test fixtures (temp DB, mock CKAN responses)
    ├── test_eda.py                         # [MVP] Test EDA functions
    ├── test_ckan.py                        # [MVP] Test CKAN client (mocked)
    ├── test_db.py                          # [MVP] Test SQLite helpers
    ├── test_llm.py                         # [MVP] Test LLM prompt/response parsing (mocked)
    ├── test_vetter.py                      # [MVP] Test vetting pipeline end-to-end
    └── test_scout.py                       # [MVP] Test scout crawl pipeline
```

## File Count Summary

| Category | MVP Files | Post-MVP Files | Total |
|---|---|---|---|
| Library (lib/) | 8 | 2 | 10 |
| Prompts | 2 | 3 | 5 |
| Agents | 4 | 2 | 6 |
| Templates | 1 | 2 | 3 |
| Tests | 7 | 0 | 7 |
| Config | 5 | 0 | 5 |
| **Total** | **27** | **9** | **36** |

## Agent Invocation

```bash
# Scout: crawl a portal, discover datasets
python agents/scout.py --portal data-gov-sg

# Vetter: vet a specific dataset at next level
python agents/vetter.py --dataset "data-gov-sg:d_abc123"

# Vetter: batch vet all level-0 datasets for a portal
python agents/vetter.py --portal data-gov-sg --level 0

# Analyst: run EDA notebook for a dataset at a level
python agents/analyst.py --dataset "data-gov-sg:d_abc123" --level 1

# Director: decide what to work on today
python agents/director.py

# Publisher: generate charts for graduated datasets
python agents/publisher.py --dataset "data-gov-sg:d_abc123"
```
