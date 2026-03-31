#!/usr/bin/env python3
"""
EDA Analyst: runs full EDA on a dataset that passed schema vetting.

Usage:
    python -m agents.analyst <dataset_id>
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from lib.db import init_db, get_conn, make_run_id
from lib.ckan import fetch_metadata, fetch_collection, fetch_to_dataframe, save_dataset, DATA_DIR
from lib.eda import basic_profile, format_profile, generate_eda_charts, save_profile_tables
from lib.llm import load_prompt, call_llm_json, DEFAULT_MODEL
from lib.artifacts import (
    write_run_artifact, ensure_human_notes, load_human_notes,
    ACTION_CODES, action_dir, ARTIFACTS_DIR,
)
from lib.flags import set_flag
from lib import notebook as nb_lib
from lib.llm_parse import join_list

ACTION = "eda"
ACTION_CODE = ACTION_CODES[ACTION]
PHASE_DIR = action_dir(ACTION_CODE, ACTION)
PROMPT_NAME = f"research-{ACTION_CODE}-{ACTION}"


def get_previous_vet(conn, dataset_id: str) -> dict | None:
    row = conn.execute(
        """SELECT verdict, verdict_reason, llm_response
           FROM runs WHERE dataset_id = ? AND action = 'vet'
           ORDER BY finished_at DESC LIMIT 1""",
        (dataset_id,),
    ).fetchone()
    if row:
        return {
            "verdict": row["verdict"],
            "reason": row["verdict_reason"],
            "full": json.loads(row["llm_response"]) if row["llm_response"] else {},
        }
    return None


def build_prompt(meta, collection, profile, eda_text, head_text, vet_summary, human_notes) -> str:
    template = load_prompt(PROMPT_NAME)
    col_lines = [f"- **{c['title']}** ({c['data_type']})" for c in meta["columns"]]
    return Template(template).safe_substitute(
        title=meta["name"],
        publisher=meta["managed_by"],
        coverage_start=(meta.get("coverage_start") or "?")[:10],
        coverage_end=(meta.get("coverage_end") or "?")[:10],
        row_count=profile["row_count"],
        description=meta.get("description", "No description"),
        column_schema="\n".join(col_lines),
        vet_summary=vet_summary,
        sample_size=profile["row_count"],
        eda_profile=eda_text,
        head_sample=head_text,
        human_notes=human_notes or "_(no human notes yet)_",
    )


def analyze_dataset(dataset_id: str, sample_limit: int = 5000) -> dict:
    steps = []
    conn = get_conn()

    # 1. Check prerequisites
    ds = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    if not ds:
        raise RuntimeError(f"Dataset {dataset_id} not found. Run vetter first.")
    if ds["rejected"]:
        raise RuntimeError(f"Dataset {dataset_id} was rejected at {ds['rejected_at_action']}.")

    # 2. Load prior vet context
    prev_vet = get_previous_vet(conn, dataset_id)
    if prev_vet:
        vet_summary = f"Verdict: {prev_vet['verdict']} | {prev_vet['reason']}"
        angles = prev_vet["full"].get("research_angles", [])
        if angles:
            vet_summary += f"\nResearch angles: {', '.join(angles)}"
        concerns = prev_vet["full"].get("concerns", [])
        if concerns:
            vet_summary += f"\nConcerns: {', '.join(concerns)}"
    else:
        vet_summary = "No previous vet found."
    steps.append({"name": "load_prior_vet", "detail": f"vet: {prev_vet['verdict']}" if prev_vet else "none found"})

    # 3. Fetch metadata
    print(f"Fetching metadata for {dataset_id}...")
    meta = fetch_metadata(dataset_id)
    print(f"  -> {meta['name']}")
    steps.append({"name": "fetch_metadata", "detail": f"{meta['name']}"})

    collection = None
    if meta["collection_ids"]:
        collection = fetch_collection(meta["collection_ids"][0])

    # 4. Load data (cached or fetch)
    cached = DATA_DIR / f"{dataset_id}.csv"
    if cached.exists():
        print(f"Using cached data: {cached}")
        df = pd.read_csv(cached)
        steps.append({"name": "load_cached_csv", "detail": f"{len(df)} rows from {cached.name}"})
    else:
        print(f"Fetching rows (limit={sample_limit})...")
        df = fetch_to_dataframe(dataset_id, limit=sample_limit)
        save_dataset(dataset_id, df)
        steps.append({"name": "fetch_rows + save_csv", "detail": f"{len(df)} rows fetched"})
    print(f"  -> {len(df)} rows loaded")
    total = ds["row_count"] or len(df)

    # 5. EDA profile
    print("Running EDA profile...")
    profile = basic_profile(df)
    eda_text = format_profile(profile)
    head_text = df.head(3).to_string()
    steps.append({"name": "basic_profile", "detail": f"{profile['row_count']} rows, {profile['col_count']} columns"})

    # 6. Generate charts + tables into {PHASE_DIR}/run-{id}/
    _temp_run_id = make_run_id()
    run_dir = ARTIFACTS_DIR / dataset_id / PHASE_DIR / f"run-{_temp_run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    chart_dir = run_dir / "charts"
    print("Generating charts...")
    chart_results = generate_eda_charts(df, chart_dir, profile)
    chart_files = [c["filename"] for c in chart_results if c["filename"]]

    # 6b. Meta-analytics tables
    table_dir = run_dir / "tables"
    table_files = save_profile_tables(df, profile, table_dir)
    print(f"  -> {len(table_files)} meta-analytics tables")
    steps.append({"name": "generate_charts_and_tables", "detail": f"{len(chart_files)} charts, {len(table_files)} tables"})

    # 7. Load human notes + build prompt
    human_notes = load_human_notes(dataset_id)
    if human_notes:
        print(f"Loaded human notes ({len(human_notes)} chars)")
        steps.append({"name": "load_human_notes", "detail": f"{len(human_notes)} chars of human feedback"})

    prompt = build_prompt(meta, collection, profile, eda_text, head_text, vet_summary, human_notes)
    print(f"Calling LLM for {ACTION} analysis...")
    analysis = call_llm_json(prompt, max_tokens=2048)
    print(f"  -> Verdict: {analysis['verdict']}")
    steps.append({"name": "call_llm_json", "detail": f"{PROMPT_NAME} -> {analysis['verdict']}"})

    # 7. Record run in DB
    run_id = _temp_run_id  # reuse the ID from chart dir
    artifact_rel = f"artifacts/{dataset_id}/{PHASE_DIR}/run-{run_id}/{ACTION_CODE}-{ACTION}-{run_id}.md"
    conn.execute(
        """INSERT INTO runs
           (id, dataset_id, action, action_code, agent, status, finished_at,
            prompt_template, llm_response, verdict, verdict_reason, artifact_paths)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id, dataset_id, ACTION, ACTION_CODE, "analyst", "done",
            datetime.now(timezone.utc).isoformat(),
            PROMPT_NAME,
            json.dumps(analysis), analysis["verdict"], analysis["reason"],
            json.dumps([artifact_rel]),
        ),
    )

    if analysis["verdict"] == "promote":
        # Advance to the next phase (engineer = 20)
        next_code = "20"
        if ds["max_action_code"] is None or ds["max_action_code"] < next_code:
            conn.execute(
                "UPDATE datasets SET max_action_code = ?, updated_at = datetime('now') WHERE id = ?",
                (next_code, dataset_id),
            )
        print(f"  -> Promoted to engineer ({next_code})")
    elif analysis["verdict"] == "reject":
        conn.execute(
            "UPDATE datasets SET rejected = 1, rejected_at_action = ?, reject_reason = ? WHERE id = ?",
            (ACTION, analysis["reason"], dataset_id),
        )

    conn.commit()
    conn.close()

    # 8. Write artifact into run dir
    context_text = f"Previous vet:\n{vet_summary}" if prev_vet else ""
    artifact_path = write_run_artifact(
        run_id=run_id, dataset_id=dataset_id, action=ACTION, action_code=ACTION_CODE,
        agent="analyst", model=DEFAULT_MODEL, title=meta["name"],
        verdict=analysis["verdict"], steps=steps, prompt_text=prompt,
        llm_response=analysis, context=context_text, charts=chart_results,
        chart_subdir="charts", output_dir=run_dir,
    )
    ensure_human_notes(dataset_id, meta["name"])
    print(f"  -> Artifact: {artifact_path}")

    # Set flags
    set_flag(dataset_id, "eda_profiled", run_id=run_id,
             detail=f"{len(chart_files)} charts, {len(table_files)} tables")
    if table_files:
        set_flag(dataset_id, "column_assessment_exists", run_id=run_id)

    # Append to session notebook (EDA is typically the first phase that runs after vet,
    # so load_or_create will create the notebook here with the setup cell)
    try:
        nb = nb_lib.load_or_create(dataset_id)
        nb_lib.add_phase_section(
            nb,
            action_code=ACTION_CODE,
            action=ACTION,
            verdict=analysis.get("verdict", "pass"),
            llm_narrative=(
                f"**Key columns:** {join_list(analysis.get('key_columns', []))}  \n"
                f"**Target column:** {analysis.get('target_col') or '(not identified yet)'}  \n"
                f"**Notable findings:** {analysis.get('summary', '')}  \n"
                f"**Quality issues:** {join_list(analysis.get('quality_issues', []))}"
            ),
            code_cells=[
                # Profile the raw dataframe
                "# EDA: basic profile\n"
                "print(df.dtypes.to_string())\n"
                "print()\n"
                "df.describe(include='all').T[['count','mean','std','min','max']].head(20)",

                # Categorical value counts
                "# Categorical column value counts\n"
                "for col in df.select_dtypes(include='object').columns[:5]:\n"
                "    print(f'\\n--- {col} ---')\n"
                "    print(df[col].value_counts().head(10))",

                # Column assessment — computed in-notebook, no file load
                "# Column assessment (reproduced in-notebook)\n"
                "import pandas as pd\n"
                "_summary = []\n"
                "for _col in df.columns:\n"
                "    _dtype = str(df[_col].dtype)\n"
                "    _miss = df[_col].isna().mean() * 100\n"
                "    _nuniq = df[_col].nunique()\n"
                "    _row = {'column': _col, 'dtype': _dtype, 'missing_pct': round(_miss, 1), 'n_unique': _nuniq}\n"
                "    if _dtype in ('float64', 'int64', 'int32'):\n"
                "        _row.update({'min': df[_col].min(), 'max': df[_col].max(), 'mean': round(df[_col].mean(), 3)})\n"
                "    else:\n"
                "        _row['top_value'] = df[_col].value_counts().index[0] if _nuniq > 0 else None\n"
                "    _summary.append(_row)\n"
                "pd.DataFrame(_summary).set_index('column')",

                # Numeric distributions
                "# Numeric feature distributions\n"
                "import matplotlib.pyplot as plt, math\n"
                "_num = df.select_dtypes(include='number').columns.tolist()[:12]\n"
                "_cols_n = 3\n"
                "_rows_n = max(1, math.ceil(len(_num) / _cols_n))\n"
                "fig, axes = plt.subplots(_rows_n, _cols_n, figsize=(13, _rows_n * 3))\n"
                "for ax, col in zip(axes.flat, _num):\n"
                "    df[col].dropna().hist(bins=40, ax=ax, color='steelblue', edgecolor='none', alpha=0.8)\n"
                "    ax.set_title(col, fontsize=9)\n"
                "for ax in axes.flat[len(_num):]:\n"
                "    ax.set_visible(False)\n"
                "plt.suptitle('Numeric Feature Distributions', fontsize=12)\n"
                "plt.tight_layout()\n"
                "plt.show()",

                # Correlation heatmap
                "# Correlation heatmap\n"
                "import matplotlib.pyplot as plt, numpy as np\n"
                "_corr = df.select_dtypes(include='number').corr()\n"
                "_sz = max(6, len(_corr))\n"
                "fig, ax = plt.subplots(figsize=(_sz, _sz * 0.85))\n"
                "_im = ax.imshow(_corr.values, cmap='RdBu_r', vmin=-1, vmax=1)\n"
                "ax.set_xticks(range(len(_corr))); ax.set_yticks(range(len(_corr)))\n"
                "ax.set_xticklabels(_corr.columns, rotation=45, ha='right', fontsize=8)\n"
                "ax.set_yticklabels(_corr.columns, fontsize=8)\n"
                "plt.colorbar(_im, ax=ax, shrink=0.8)\n"
                "ax.set_title('Correlation Matrix')\n"
                "plt.tight_layout()\n"
                "plt.show()",
            ],
        )
        nb_lib.save(nb, dataset_id)
        print(f"  Notebook updated: session.ipynb")
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"  Notebook write failed: {e}")

    return analysis


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m agents.analyst <dataset_id>")
        sys.exit(1)

    analysis = analyze_dataset(sys.argv[1])
    print(f"\n=== EDA Complete ===")
    print(f"Verdict: {analysis['verdict']}")
    print(f"Reason:  {analysis['reason']}")


if __name__ == "__main__":
    main()
