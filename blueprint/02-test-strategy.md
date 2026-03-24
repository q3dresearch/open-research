# Test Strategy
<!-- version: 0.1 | phase: 2 | last-updated: 2026-03-25 -->

## Testing Stack

| Tool | Purpose |
|---|---|
| pytest | Unit and integration tests |
| pytest fixtures | Temp SQLite DB, mock CKAN responses, mock Claude API |
| unittest.mock | Mock external services (CKAN, Claude API) |
| nbformat | Validate generated notebooks are well-formed |
| sqlite3 | Direct DB assertions |

## Test Levels

### Level 1: Smoke Tests (run on every change)

Quick sanity checks that core functions work.

```
- [ ] SQLite DB initializes with correct schema (lib/db.py)
- [ ] CKAN client can parse a sample API response (lib/ckan.py)
- [ ] EDA functions return expected shapes on a sample DataFrame (lib/eda.py)
- [ ] LLM wrapper handles well-formed and malformed responses (lib/llm.py)
- [ ] Notebook template loads and can be parameterized (lib/notebooks.py)
```

**Run command:** `pytest tests/ -m smoke`
**When:** Before every commit.

### Level 2: Unit Tests (run on every change)

Test individual library functions in isolation.

```
Priority order:
1. lib/eda.py — getMissingValues, getMinMax, getSample, getCardinality
   - Test with clean data, missing data, single-column, empty DataFrame
2. lib/db.py — upsert_dataset, get_datasets_at_level, update_level, log_run
   - Test with fresh DB, duplicate inserts, concurrent-like sequences
3. lib/ckan.py — parse_catalog, parse_resource_schema, download_resource
   - Test with mock CKAN JSON responses (valid, malformed, empty)
4. lib/llm.py — send_prompt, parse_verdict, estimate_cost
   - Test with mock Claude responses (pass, reject, malformed JSON)
5. lib/charts.py — generate_trend, generate_histogram, generate_heatmap
   - Test output is valid PNG/SVG, correct dimensions, has title
6. lib/cache.py — download_to_cache, cleanup_low_level, get_cached_path
   - Test with mock downloads, cleanup threshold logic
7. lib/transforms.py [P1] — panel_convert, group_delta, time_decompose
   - Test with known DataFrames, verify output shapes and values
8. lib/embeddings.py [P1] — embed_schema, cosine_search, find_similar
   - Test with mock embeddings, verify ranking order
```

**Run command:** `pytest tests/ -m unit`
**Coverage target:** 80% of lib/ directory

### Level 3: Integration Tests (run before milestones)

Test that agents work end-to-end with mocked external services.

```
Priority order:
1. Scout pipeline: mock CKAN → scout.py → datasets in DB at level 0
2. Vetter pipeline: dataset at level 0 + mock Claude → vetter.py → level 1 or rejected
3. Analyst pipeline: dataset at level 1 + mock data → analyst.py → notebook + charts generated
4. Full flow: scout → vetter → analyst on a single dataset (all mocked)
5. Director decision: given various game states → director picks correct action
```

**Run command:** `pytest tests/ -m integration`

### Level 4: Live Smoke Test (run manually before gates)

Actually hit the real CKAN API and Claude API with a single known dataset.

```
1. Scout: crawl data.gov.sg, verify ≥100 datasets discovered
2. Vetter: schema-vet 5 known datasets, verify verdicts are reasonable
3. Analyst: run lv1 EDA on 1 known dataset, verify notebook and charts exist
```

**Run command:** `pytest tests/ -m live --live` (requires `--live` flag to prevent accidental API calls)
**When:** Before Gate reviews only. Costs real API credits.

## Test Database

- Tests create a temporary SQLite DB in `/tmp/` or pytest's `tmp_path`
- Each test function gets a fresh DB (fixture creates + migrates + yields + deletes)
- No shared state between tests

## Mock Strategy

### Mock CKAN API
```python
# Fixture provides sample CKAN responses from tests/fixtures/
# - ckan_catalog.json: sample package_list response
# - ckan_resource.json: sample resource metadata
# - ckan_data.csv: sample dataset (10 rows)
```

### Mock Claude API
```python
# Fixture provides canned LLM responses:
# - verdict_pass.json: {"verdict": "pass", "reason": "...", "score": 7}
# - verdict_reject.json: {"verdict": "reject", "reason": "...", "score": 2}
# - malformed.txt: unparseable response (test error handling)
```

## What NOT to Test

- Claude API internals (trust the SDK — mock it)
- CKAN API internals (mock it)
- pandas internals (trust the library)
- SQLite engine behavior (trust it)
- Notebook rendering in Jupyter UI

## What TO Test Carefully

- **Prompt template rendering** — variables actually get substituted
- **Verdict parsing** — handles all response formats (JSON, freetext, malformed)
- **DB state transitions** — level-up, rejection, cron_levels updates are atomic and correct
- **Idempotency** — running the same agent twice on the same dataset doesn't corrupt state
- **Cost tracking** — cost_estimate_usd is populated and reasonable

## When Tests Fail

```
1. Read the error message
2. Check if it's a real bug or a test environment issue
3. If real bug:
   a. Write a failing test that reproduces it
   b. Fix the bug in lib/ or agents/
   c. Verify test passes
   d. Log in the run's decision log if it affected a live dataset
4. If flaky test:
   a. Fix the test (usually a timing or fixture issue)
   b. Add a comment explaining what was flaky
```
