# Variables Registry
<!-- version: 0.1 | phase: 1 | last-updated: 2026-03-24 -->

<!--
  INSTRUCTIONS FOR AI:
  This is the master variable registry. ALL templates reference these variables.
  During Phase 1 (Q&A), populate the "Value" column.
  During Phase 2 (Architecture), populate stack and architecture variables.
  When ANY variable changes, grep all 01-*.md and 02-*.md files and update every occurrence.
  Never leave a {{VARIABLE}} unresolved in a non-template file.
-->

## Project Identity

| Variable | Value | Set In Phase | Notes |
|---|---|---|---|
| `{{PROJECT_NAME}}` | open-research | 1 | Public output repo under q3dresearch org |
| `{{ONE_LINER}}` | AI agent that autonomously discovers, vets, and analyzes public datasets from CKAN portals, producing publication-ready charts and recurring alerts when indicators move | 1 | |
| `{{TARGET_USER}}` | Operator/researcher (self) first; downstream: data-curious citizens, urbanists, policy teams who consume published outputs | 1 | |
| `{{CORE_ACTION}}` | Shortlist → research → graduate datasets through tiers → publish | 1 | |
| `{{PRIMARY_ENTITY}}` | Dataset (a single table/resource from a public portal) | 1 | |
| `{{MONETIZATION_MODEL}}` | None — open research pipeline. Value is in published signals and methodology | 1 | |

## User & Access

| Variable | Value | Set In Phase | Notes |
|---|---|---|---|
| `{{USER_ROLES}}` | operator (human reviewer), ai-agent (Claude running research), consumer (reads outputs) | 1 | |
| `{{MULTI_TENANT}}` | No — single research org (q3dresearch) | 1 | |
| `{{AUTH_PROVIDER}}` | N/A (no web app) | 1 | |
| `{{AUTH_STRATEGY}}` | GitHub repo access + Claude API key | 1 | |

## Stack Decisions

| Variable | Value | Justification | Set In Phase |
|---|---|---|---|
| `{{FRAMEWORK}}` | Python scripts + Claude Code agents | Research pipeline, not a web app | 1 |
| `{{LANGUAGE}}` | Python | Data science ecosystem (pandas, matplotlib) | 1 |
| `{{STYLING}}` | N/A | | |
| `{{UI_LIBRARY}}` | N/A | | |
| `{{PAYMENT_PROVIDER}}` | N/A | | |
| `{{DB_PROVIDER}}` | SQLite3 | Simple, portable, open-sourceable as a file | 1 |
| `{{DB_ORM}}` | Raw SQL or sqlite3 stdlib | Minimal deps | 1 |
| `{{HOSTING}}` | GitHub (repo) + local/cron (compute) | Outputs committed to open-research repo | 1 |
| `{{EMAIL_PROVIDER}}` | N/A | | |
| `{{FILE_STORAGE}}` | Git repo (charts, notebooks, manifests) | | 1 |
| `{{ANALYTICS}}` | N/A | | |

## Architecture Decisions

| Variable | Value | Set In Phase | Notes |
|---|---|---|---|
| `{{SUBSCRIPTION_TYPE}}` | N/A | 1 | Not a SaaS |
| `{{SUBSCRIPTION_PLANS}}` | N/A | 1 | |
| `{{API_STYLE}}` | N/A — CLI/agent-driven | 1 | |
| `{{DB_RELATIONS}}` | portals → datasets → runs → artifacts | 1 | |
| `{{SECONDARY_ENTITIES}}` | Portal, Run, Artifact, Signal, JoinProposal | 1 | |
| `{{KEY_INTEGRATIONS}}` | CKAN APIs, Claude API (LLM judge), data.gov.sg | 1 | |

## MVP Scoping Flags

| Variable | Value | Set In Phase | Notes |
|---|---|---|---|
| `{{REALTIME_NEEDED}}` | No | 1 | Batch/cron only |
| `{{BACKGROUND_JOBS_NEEDED}}` | Yes — cron for re-running graduated research pipelines | 1 | Core to the product |
| `{{CACHING_NEEDED}}` | No — SQLite is the cache | 1 | |
| `{{ADMIN_PANEL_NEEDED}}` | No — operator reads SQLite + artifacts directly | 1 | |
| `{{FILE_UPLOAD_NEEDED}}` | No — datasets fetched from portals | 1 | |
| `{{SEARCH_NEEDED}}` | No (v1) | 1 | |
| `{{NOTIFICATIONS_NEEDED}}` | No (v1) — operator checks outputs manually | 1 | |

## Domain-Specific

| Variable | Value | Set In Phase | Notes |
|---|---|---|---|
| `{{CORE_USER_ACTION}}` | Add portal URL → AI vets and researches datasets autonomously | 1 | |
| `{{PORTAL_REGISTRY}}` | Fixed list of CKAN portal URLs in config/SQLite. Append new ones to expand scope | 1 | |
| `{{VETTING_TIERS}}` | research-00-schema-vet, research-01-lv1-eda-vet, research-02-lv2-eda-vet (extensible — add research-NN for new tiers) | 1 | Graduated prompt chain |
| `{{RESEARCH_LIBRARY}}` | Python library (eda.py, transforms.py, etc.) with composable functions. Notebooks import library and call functions in sequence. Library grows over time: getMissingValues → getPermutationScores → getVIFplot | 1 | Notebooks stay thin: sequence + results + LLM commentary |
| `{{ARTIFACT_FORMAT}}` | Jupyter notebook per run per schema per level (imports research library) + decision logs + head/tail | 1 | Notebooks are artifact of record |
| `{{ARTIFACT_REUSE}}` | Researcher agent has a search function over past decisions — not prompt stuffing. Finds similar schemas via embedding similarity, compares first AI attempt vs final human-curated path | 1 | Gap between AI first attempt and human final = institutional knowledge |
| `{{SCHEMA_SIMILARITY}}` | Embed each table's column names + descriptions into a vector. Start with flat numpy array + Claude API embeddings. Graduate to sqlite-vec when >5000 schemas | 1 | O(n) cosine similarity is fine at current scale |
| `{{DB_SCALING}}` | SQLite committed to repo. If >50MB, migrate to Convex/Neon/Turso | 1 | |
| `{{OBSERVATORY_DB}}` | q3dresearch/observatory — SQLite DB of all portal/dataset/run metadata, open-sourceable | 1 | |
| `{{SCHEMA_JOINING}}` | ProposedJoins table (ai/human proposals, status). Approved → SyntheticTables (provenance, transform process, own notebook, enters same level system) | 1 | |
| `{{RAW_DATA_CACHE}}` | Downloaded data lives locally, never committed. Cron cleans up low-level rejects. High-level datasets keep cache longer | 1 | |
| `{{LV2_COLLABORATION}}` | lv2+ is a human-AI loop: AI runs first traverse → human reviews → proposes own path → AI reruns → loop until settled. Human adds metadata/notes for future levels to reference | 1 | Notebooks are living collaboration docs |
| `{{CRON_CONTROL}}` | AI proposes cron_levels, human sets and toggles. Low bandwidth, high control | 1 | |
| `{{PUBLISHER_MODE}}` | Start manual (operator reviews outputs, posts). When predictable, operator writes cron instruction (possibly deterministic script) | 1 | |

## Game Model (Research Simulator)

### Dataset State: Two Columns

| Variable | Value | Set In Phase | Notes |
|---|---|---|---|
| `{{MAX_LEVEL}}` | int — highest tier completed. Level 0=discovered, 1=schema-vetted, 2=basic-EDA, 3=advanced-EDA, ...N | 1 | Only goes up as analysis deepens |
| `{{CRON_LEVELS}}` | array of ints — which levels are actively cron'd. e.g. [1,3] = run lv1 and lv3 notebooks on schedule. Empty = not producing output | 1 | A lv3 dataset can cron [1] for high-freq stats + [3] monthly. Any cron can be toggled off for cost |
| `{{GRADUATED}}` | Derived: len(cron_levels) > 0. Not a stored flag — it's "is this producing income?" | 1 | |

### Game Phases

| Variable | Value | Set In Phase | Notes |
|---|---|---|---|
| `{{EARLYGAME}}` | Discover portals, vet datasets, build base of level-0 → 1 → 2 rows | 1 | |
| `{{MIDGAME}}` | Activate cron_levels on proven datasets while still vetting new ones upward | 1 | |
| `{{ENDGAME}}` | Maximize passive cron'd datasets. Discover joins across high-level datasets | 1 | |
| `{{GAME_OBJECTIVE}}` | Most number of datasets with active cron_levels (passive gold mines). No max level required — just useful output at any tier | 1 | |

### Agent Roles (Characters — editable anytime)

| Variable | Value | Set In Phase | Notes |
|---|---|---|---|
| `{{AGENT_DIRECTOR}}` | Master data scientist. Daily priorities: vet new? rerun? join? Delegates to specialists | 1 | Quest board |
| `{{AGENT_SCOUT}}` | Crawls portals, discovers datasets, fills level-0 rows | 1 | Explorer |
| `{{AGENT_VETTER}}` | Runs research-00..N prompts, levels up max_level or rejects | 1 | Appraiser |
| `{{AGENT_ANALYST}}` | Runs EDA notebooks, produces artifacts per level | 1 | Researcher |
| `{{AGENT_CARTOGRAPHER}}` | Proposes cross-dataset joins for high-level datasets | 1 | Diplomat |
| `{{AGENT_PUBLISHER}}` | Separate cron, separate config. Operator says what to publish + frequency. Checks main table for datasets with active cron_levels + ready artifacts. Does not decide what to research — only what to yell | 1 | Town crier — decoupled |

### Quest Log = Artifacts

| Variable | Value | Set In Phase | Notes |
|---|---|---|---|
| `{{QUEST_LOG}}` | Each agent's work inspectable: notebooks, charts, decision logs per dataset per run per level | 1 | Audit + positive/negative examples for future context |
