#!/usr/bin/env python3
"""
Phase 00 Vetter — schema and quality gate before pipeline entry.

Evaluates a dataset using LLM judgment on metadata + EDA profile.

Usage:
    python -m agents.vetter <dataset_id>
    python -m agents.vetter --next          # pick next pending from scan_catalog
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.db import init_db, RunContext
from lib.ckan import fetch_metadata, fetch_collection, fetch_rows, fetch_to_dataframe, save_dataset, DATA_DIR
from lib.eda import basic_profile, format_profile
from lib.llm import load_prompt, call_llm_json, DEFAULT_MODEL
from lib.artifacts import write_run_artifact, ensure_human_notes, ACTION_CODES, action_dir
from lib.flags import set_flag
import pandas as pd

ACTION = "vet"
ACTION_CODE = ACTION_CODES[ACTION]
PHASE_DIR = action_dir(ACTION_CODE, ACTION)
PROMPT_NAME = f"research-{ACTION_CODE}-{ACTION}"


def build_prompt(meta: dict, collection: dict | None, profile: dict, eda_text: str) -> str:
    template = load_prompt(PROMPT_NAME)
    col_lines = [f"- **{c['title']}** ({c['data_type']})" for c in meta["columns"]]
    return Template(template).safe_substitute(
        title=meta["name"],
        publisher=meta["managed_by"],
        format=meta["format"],
        coverage_start=(meta.get("coverage_start") or "?")[:10],
        coverage_end=(meta.get("coverage_end") or "?")[:10],
        frequency=collection["frequency"] if collection else "unknown",
        row_count=profile["row_count"],
        description=meta.get("description", "No description"),
        column_schema="\n".join(col_lines),
        sample_size=profile["row_count"],
        eda_profile=eda_text,
    )


def vet_dataset(dataset_id: str) -> dict:
    # Guard: never re-vet a dataset that's already recorded as rejected in the DB.
    # The rejection reason is preserved in datasets.reject_reason + runs.llm_response.
    conn = init_db()
    existing = conn.execute(
        "SELECT rejected, reject_reason FROM datasets WHERE id = ?", (dataset_id,)
    ).fetchone()
    conn.close()
    if existing and existing["rejected"]:
        reason = existing["reject_reason"] or "no reason recorded"
        print(f"  -> Skipping {dataset_id}: already rejected ({reason})")
        return {"verdict": "fail", "score": 0, "reason": reason, "skipped": True}

    steps = []
    ctx = RunContext(dataset_id, ACTION, ACTION_CODE, "vetter")
    conn = ctx.conn

    # 1. Fetch metadata
    print(f"Fetching metadata for {dataset_id}...")
    meta = fetch_metadata(dataset_id)
    print(f"  -> {meta['name']}")
    steps.append({"name": "fetch_metadata", "detail": f"{meta['name']} — {len(meta['columns'])} columns, {meta['managed_by']}"})

    collection = None
    if meta["collection_ids"]:
        collection = fetch_collection(meta["collection_ids"][0])
        if collection:
            steps.append({"name": "fetch_collection", "detail": f"{collection['name']} — {collection['frequency']}, {len(collection['child_datasets'])} siblings"})

    # 1b. Size gate — skip datasets whose catalog file size exceeds 500 MB.
    #     scan_catalog.size_bytes is set by the discover scanner.
    #     Manually-added datasets (not in scan_catalog) skip this check.
    MAX_FILE_BYTES = 500 * 1024 * 1024  # 500 MB
    conn2 = init_db()
    cat_row = conn2.execute(
        "SELECT size_bytes FROM scan_catalog WHERE id = ?", (dataset_id,)
    ).fetchone()
    conn2.close()
    if cat_row and cat_row["size_bytes"] and cat_row["size_bytes"] > MAX_FILE_BYTES:
        size_mb = cat_row["size_bytes"] / 1_048_576
        print(f"  -> Skipping {dataset_id}: catalog size {size_mb:.0f} MB > 500 MB limit")
        return {"verdict": "skip", "score": 0,
                "reason": f"too_large: {size_mb:.0f} MB in catalog", "skipped": True}

    # 2. Fetch sample rows (use cache if available)
    cached = DATA_DIR / f"{dataset_id}.csv"
    if cached.exists():
        print(f"Using cached data: {cached}")
        df = pd.read_csv(cached)
        steps.append({"name": "load_cached_csv", "detail": f"{len(df)} rows from {cached.name}"})
    else:
        print("Fetching sample rows...")
        df = fetch_to_dataframe(dataset_id, limit=500)
        save_dataset(dataset_id, df)
        steps.append({"name": "fetch_rows + save_csv", "detail": f"{len(df)} rows fetched and saved"})

    # Get total from API or cache
    total = len(df)
    try:
        result = fetch_rows(dataset_id, limit=1)
        total = result.get("total", total)
    except Exception:
        pass  # use len(df) if API unavailable

    # 3. EDA profile
    print("Running EDA profile...")
    profile = basic_profile(df)
    eda_text = format_profile(profile)
    steps.append({"name": "basic_profile", "detail": f"{profile['row_count']} rows, {profile['col_count']} columns profiled"})

    # 4. LLM call
    prompt = build_prompt(meta, collection, profile, eda_text)
    print("Calling LLM for schema vet...")
    verdict = call_llm_json(prompt)
    print(f"  -> Verdict: {verdict['verdict']} (score: {verdict['score']})")
    steps.append({"name": "call_llm_json", "detail": f"{PROMPT_NAME} -> {verdict['verdict']} (score {verdict['score']})"})

    # 5. Register in DB
    conn.execute(
        "INSERT OR IGNORE INTO portals (id, url, name, api_type) VALUES (?, ?, ?, ?)",
        ("data-gov-sg", "https://data.gov.sg", "Data.gov.sg", "ckan"),
    )
    pipeline_type = verdict.get("pipeline_type", "transactional")
    conn.execute(
        """INSERT OR REPLACE INTO datasets
           (id, portal_id, resource_url, title, description, schema_shape,
            format, row_count, pipeline_type, update_frequency, max_action_code)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            dataset_id, "data-gov-sg",
            f"https://data.gov.sg/datasets/{dataset_id}/view",
            meta["name"], meta["description"], json.dumps(meta["columns"]),
            meta["format"], total, pipeline_type,
            collection["frequency"] if collection else "unknown",
            ACTION_CODE,
        ),
    )

    run_id = ctx.run_id
    ctx.finish(
        verdict=verdict["verdict"],
        verdict_reason=verdict["reason"],
        llm_response=json.dumps(verdict),
        artifact_paths=[f"artifacts/{dataset_id}/{ACTION_CODE}-{ACTION}-{run_id}.md"],
        prompt_template=PROMPT_NAME,
    )

    if verdict["verdict"] == "fail":
        conn.execute(
            "UPDATE datasets SET rejected = 1, rejected_at_action = ?, reject_reason = ? WHERE id = ?",
            (ACTION, verdict["reason"], dataset_id),
        )

    # Mark candidate as vetted if it came through discovery
    conn.execute(
        "UPDATE scan_catalog SET status = 'vetted', vetted_at = datetime('now') WHERE id = ?",
        (dataset_id,),
    )

    conn.commit()
    ctx.close()

    # 6. Write artifact
    artifact_path = write_run_artifact(
        run_id=run_id, dataset_id=dataset_id, action=ACTION, action_code=ACTION_CODE,
        agent="vetter", model=DEFAULT_MODEL, title=meta["name"],
        verdict=verdict["verdict"], steps=steps, prompt_text=prompt,
        llm_response=verdict,
    )
    ensure_human_notes(dataset_id, meta["name"])
    print(f"  -> Artifact: {artifact_path}")

    if verdict["verdict"] == "pass":
        set_flag(dataset_id, "schema_vetted", run_id=run_id,
                 detail=f"pass, score={verdict.get('score', '?')}")

    return verdict


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_id", nargs="?", help="Dataset ID to vet")
    parser.add_argument("--next", action="store_true",
                        help="Pick the next pending CSV from scan_catalog and vet it")
    args = parser.parse_args()

    if args.next:
        conn = init_db()
        row = conn.execute(
            "SELECT id, name FROM scan_catalog WHERE status='pending' AND format='CSV' ORDER BY size_bytes DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            print("No pending items in scan_catalog. Run agents/discover.py first.")
            sys.exit(0)
        dataset_id = row["id"]
        print(f"Next from catalog: {row['name']}  ({dataset_id})\n")
    elif args.dataset_id:
        dataset_id = args.dataset_id
    else:
        parser.print_usage()
        sys.exit(1)

    verdict = vet_dataset(dataset_id)
    print(f"\n=== Schema Vet Complete ===")
    print(f"Verdict:  {verdict['verdict']} ({verdict['score']}/10)")
    print(f"Type:     {verdict.get('pipeline_type', 'transactional')}")
    print(f"Reason:   {verdict['reason']}")


if __name__ == "__main__":
    main()
