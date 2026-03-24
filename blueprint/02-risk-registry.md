# Risk Registry
<!-- version: 0.1 | phase: 2 | last-updated: 2026-03-25 -->

## Risk Severity Scale

| Level | Impact | Response |
|---|---|---|
| Critical | Pipeline broken, data corruption, cost runaway | Must fix before next run |
| High | Major feature degraded, wrong results | Fix within current milestone |
| Medium | Minor issue, workaround exists | Schedule for next milestone |
| Low | Cosmetic or edge case | Backlog |

## Data & API Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| CKAN API changes or goes down | High | Medium | Cache last-known catalog in SQLite. Scout is idempotent — re-run when API recovers. Abstract CKAN calls behind `lib/ckan.py` interface |
| Dataset format changes upstream (new columns, renamed fields) | Medium | High | Schema-vet re-runs will detect drift. Store `schema_shape` at discovery time and diff on re-crawl. Log schema changes in runs table |
| Dataset is too large to download (>1GB CSV) | Medium | Medium | `lib/cache.py` streams downloads, checks Content-Length before committing. Set a configurable max size. Skip or sample oversized datasets |
| Dataset URL goes dead (404) | Low | Medium | Log download failures in runs table. Don't reject — mark as `stale` and retry next crawl. Alert operator if a graduated dataset goes dead |
| Portal rate-limits our crawler | Medium | Medium | `tenacity` retry with exponential backoff in `lib/ckan.py`. Configurable delay between requests. Respect Retry-After headers |
| Encoding issues in downloaded CSVs | Medium | High | Try UTF-8 → latin-1 → cp1252 fallback chain in `lib/cache.py`. Log encoding used per dataset |

## LLM / Claude API Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Claude API rate limit or downtime | High | Low | Retry with backoff. Queue runs that fail due to API issues. Don't crash the pipeline — log and continue to next dataset |
| LLM misjudges a dataset (false positive or negative) | Medium | High | This is expected and designed for. Decision logs enable human review. Operator can override any verdict. Over time, similarity search provides better context |
| LLM produces malformed structured output | High | Medium | `lib/llm.py` validates response format. If parse fails, log raw response and mark run as `failed` (not `rejected`). Retry once with format reminder in prompt |
| Prompt template produces inconsistent results | Medium | Medium | Pin prompt versions in runs table (`prompt_template` column). A/B test prompt changes by comparing verdict distributions |
| Cost spike from large batch runs | High | Medium | `cost_estimate_usd` tracked per run. Director agent checks cumulative daily spend before dispatching. Hard budget cap configurable in `portals.yaml` |
| Context window exceeded (large schema or EDA output) | Medium | Medium | Truncate EDA stats to top-N columns by interest. Summarize rather than dump full head/tail. Track token count per run |

## Database Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| SQLite file corruption | Critical | Low | Back up before every batch run. Git commit history provides versioned backups. SQLite WAL mode for crash safety |
| SQLite file grows too large for git | Medium | Low | Monitor file size. At ~50MB, evaluate migration to Turso or committed DB + LFS. Artifacts (notebooks, charts) are separate files — DB stays metadata-only |
| Concurrent write conflicts (two agents running simultaneously) | Medium | Medium | SQLite WAL mode allows concurrent reads. Serialize writes through `lib/db.py` with retry on SQLITE_BUSY. Design agents to be idempotent |
| Schema migration breaks existing data | High | Low | Always backup before migration. Migrations are idempotent SQL files. Test on a copy first |

## Pipeline / Agent Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Scout discovers 10,000 datasets — vetting cost explodes | High | Medium | Director enforces a daily budget. Vet in batches (e.g., 50 schema-vets per day). Prioritize by metadata signals (recently updated, popular) |
| Notebook execution fails (papermill error, missing dependency) | Medium | High | Wrap execution in try/catch. Log the traceback in runs table. Mark run as `failed`. Don't block other datasets |
| Agent runs on stale data (cached CSV is outdated) | Medium | Medium | Check CKAN `last_modified` metadata before running. Re-download if newer version exists. Log data freshness per run |
| Artifacts folder grows unbounded | Low | High | Graduated datasets accumulate charts and notebooks. Implement artifact retention policy: keep last N runs, archive older ones. Monitor total artifact size |
| Feature engineering in lv2 produces meaningless features | Medium | High | This is expected — lv2 is a human-AI loop. AI proposes, human reviews. Bad features are part of the quest log (negative examples for future runs) |
| Director agent enters infinite loop (always picks same task) | Medium | Low | Director logs its decision reasoning. Add a "last N decisions" check — flag if same dataset picked 3+ times in a row |

## Infrastructure Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| GitHub outage prevents artifact commits | Low | Low | Artifacts exist locally first. Commit when GitHub recovers. Pipeline doesn't depend on GitHub being up to run |
| GitHub repo hits size limit (free tier: 1GB soft, 5GB hard) | Medium | Low | Artifacts are mostly small (notebooks, PNGs). Monitor repo size. If approaching limit, archive old artifacts to a release or external storage |
| Papermill fails to execute a notebook (dependency missing, kernel crash) | Medium | High | `lib/notebooks.py` wraps execution in try/catch. Log traceback in runs table. Mark run as `failed`. Ensure virtual environment has all deps. Pin notebook kernel to project's Python |
| Jupyter notebook format changes in nbformat upgrade | Low | Low | Pin nbformat version. Template notebooks validated in smoke tests |

## Operational Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Lost work when switching devices | Medium | Low | Everything is in git. Commit frequently. The `.db` file is committed. Only `data/` (raw cache) is local-only |
| Claude API key leaked in committed file | Critical | Low | `.env` file for API key, gitignored. Never hardcode keys. Use `.env.example` as template |
| Operator forgets to review decisions | Low | High | Not a risk to the system — it keeps running. But quality degrades without human steering. Consider a weekly review ritual |
| Multiple devices run agents simultaneously | Medium | Medium | SQLite handles this poorly. Convention: only one device runs agents at a time. Use a lockfile or check `runs.status = 'running'` before starting |

## Cost Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Uncontrolled Claude API spend | High | Medium | Track `cost_estimate_usd` per run. Director checks daily cumulative before dispatching. Hard cap in config. Operator reviews spend weekly |
| Graduated dataset's cron runs even when data hasn't changed | Low | Medium | Check `last_modified` from CKAN before re-running. Skip if unchanged. Log "skipped — no new data" |

## Risk Review Schedule

- **Every gate:** Check all High and Critical risks
- **Weekly:** Review run costs, check for failed runs, review rejection quality
- **Monthly:** Review artifact size, DB size, prompt effectiveness
