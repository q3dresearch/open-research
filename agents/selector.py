#!/usr/bin/env python3
"""
Level 3 Selector — staged feature selection for publication readiness.

Runs a 6-stage pipeline (cheap → expensive) to identify high-signal columns,
then asks the LLM to review and finalize the feature set.

Stages:
  1. Cheap pruning (missingness, variance, ID-like)
  2. Correlation clustering (keep one representative per cluster)
  3. Pseudo-target discovery (predict each column from others → redundancy)
  4. Lightweight supervised scoring (MI, correlation with target)
  5. Expensive attribution (SHAP on survivors only)
  6. Chart filter (retain time/category for publication)

Usage:
    python -m agents.selector <dataset_id> [--target <col>] [--no-shap]
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from lib.db import get_conn, make_run_id
from lib.ckan import fetch_metadata, DATA_DIR
from lib.eda import basic_profile, format_profile
from lib.eda.selection import run_selection_pipeline, SelectionReport
from lib.llm import load_prompt, call_llm_json, DEFAULT_MODEL
from lib.artifacts import (
    write_run_artifact, ensure_human_notes, load_human_notes,
    load_prior_artifacts, ARTIFACTS_DIR, ACTION_CODES, action_dir,
)
from lib.flags import set_flag
from lib import notebook as nb_lib
from lib.llm_parse import join_list, as_str_list

ACTION = "select"
ACTION_CODE = ACTION_CODES[ACTION]
PHASE_DIR = action_dir(ACTION_CODE, ACTION)
PROMPT_NAME = f"research-{ACTION_CODE}-{ACTION}"

# References to other phases
CLEAN_CODE = ACTION_CODES["clean"]
CLEAN_DIR = action_dir(CLEAN_CODE, "clean")
ENGINEER_DIR = action_dir(ACTION_CODES["engineer"], "engineer")
CLUSTER_CODE = ACTION_CODES["cluster"]
CLUSTER_DIR = action_dir(CLUSTER_CODE, "cluster")
EDA_DIR = action_dir(ACTION_CODES["eda"], "eda")


def get_engineer_dir(dataset_id: str) -> Path:
    return ARTIFACTS_DIR / dataset_id / ENGINEER_DIR


def get_phase_dir(dataset_id: str) -> Path:
    d = ARTIFACTS_DIR / dataset_id / PHASE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_run_dir(dataset_id: str, run_id: str) -> Path:
    d = get_phase_dir(dataset_id) / f"run-{run_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_pipeline_and_run(dataset_id: str) -> tuple[pd.DataFrame, str, int]:
    """Load full CSV, replay clean → engineer pipelines, attach cluster labels.

    Returns (df, pipeline_summary, step_count).
    """
    import importlib.util

    csv_path = DATA_DIR / f"{dataset_id}.csv"
    if not csv_path.exists():
        raise RuntimeError(f"No data file at {csv_path}. Download full dataset first.")

    raw_df = pd.read_csv(csv_path)
    df = raw_df.copy()
    summary_parts = []
    total_steps = 0

    # 1. Replay clean pipeline if exists
    clean_pipeline_path = ARTIFACTS_DIR / dataset_id / CLEAN_DIR / "clean_pipeline.py"
    if clean_pipeline_path.exists():
        spec = importlib.util.spec_from_file_location("clean_pipeline", clean_pipeline_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        df = mod.run_pipeline(df)
        clean_steps = [s.__name__ for s in mod.STEPS]
        total_steps += len(clean_steps)
        summary_parts.append(f"Clean ({len(clean_steps)} steps):")
        summary_parts.extend(f"  {i+1}. {name}" for i, name in enumerate(clean_steps))

    # 2. Replay engineer pipeline if exists
    pipeline_path = get_engineer_dir(dataset_id) / "pipeline.py"
    if pipeline_path.exists():
        spec = importlib.util.spec_from_file_location("pipeline", pipeline_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        df = mod.run_pipeline(df)
        eng_steps = [s.__name__ for s in mod.STEPS]
        total_steps += len(eng_steps)
        summary_parts.append(f"Engineer ({len(eng_steps)} steps):")
        summary_parts.extend(f"  {i+1}. {name}" for i, name in enumerate(eng_steps))

    # 3. Attach cluster labels if they exist (index-join, tolerates row-count mismatches)
    cluster_labels_path = ARTIFACTS_DIR / dataset_id / CLUSTER_DIR / "cluster_labels.csv"
    if cluster_labels_path.exists():
        labels_df = pd.read_csv(cluster_labels_path, index_col=0)
        label_cols = [c for c in labels_df.columns if c in ("cluster_label", "cluster_name")]
        if label_cols:
            df = df.join(labels_df[label_cols], how="left")
            summary_parts.append(f"Cluster labels attached: {', '.join(label_cols)}")

    if not summary_parts:
        return df, "(no pipelines found)", 0

    return df, "\n".join(summary_parts), total_steps


def guess_target(df: pd.DataFrame, human_notes: str | None) -> str | None:
    """Heuristic: pick the most likely prediction target.

    Looks for columns with 'price', 'target', 'label' in the name.
    Falls back to the last numeric column.
    """
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if not numeric_cols:
        return None

    # Check human notes for target hints
    if human_notes:
        notes_lower = human_notes.lower()
        for col in numeric_cols:
            if col.lower() in notes_lower:
                # Mentioned in notes = likely important
                if any(kw in col.lower() for kw in ["price", "target", "label", "value", "score"]):
                    return col

    # Keyword match
    for col in numeric_cols:
        col_lower = col.lower()
        if any(kw in col_lower for kw in ["resale_price", "target", "label"]):
            return col

    for col in numeric_cols:
        if "price" in col.lower() and "log" not in col.lower() and "per" not in col.lower():
            return col

    return None


def format_report_for_llm(report: SelectionReport) -> dict:
    """Format selection report sections for the prompt template."""
    # Stage summaries
    stage_lines = []
    for s in report.stage_summaries:
        stage_lines.append(
            f"Stage {s['stage']} ({s['name']}): "
            f"{s.get('input_cols', '?')} → {s.get('survivors', '?')} cols "
            f"(dropped {s.get('dropped', 0)})"
        )
    stage_summaries = "\n".join(stage_lines)

    # Dropped columns
    dropped_lines = []
    for d in report.dropped:
        dropped_lines.append(f"  - {d['column']} [stage {d['stage']}]: {d['reason']}")
    dropped_columns = "\n".join(dropped_lines) if dropped_lines else "(none dropped)"

    # Scored columns
    scored_lines = []
    for col in report.kept:
        scores = report.scores.get(col, {})
        score_parts = []
        for k, v in scores.items():
            if v is not None:
                score_parts.append(f"{k}={v}")
        score_str = ", ".join(score_parts) if score_parts else "no scores"
        scored_lines.append(f"  - {col}: {score_str}")
    scored_columns = "\n".join(scored_lines)

    # Chart retained
    chart_lines = []
    for c in report.chart_retained:
        chart_lines.append(f"  - {c['column']}: {c['reason']}")
    chart_retained = "\n".join(chart_lines) if chart_lines else "(none flagged)"

    return {
        "stage_summaries": stage_summaries,
        "dropped_columns": dropped_columns,
        "scored_columns": scored_columns,
        "chart_retained": chart_retained,
    }


def _save_chart(fig, path):
    fig.savefig(path, dpi=120, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def generate_selection_charts(df: pd.DataFrame, report: SelectionReport,
                              target_col: str | None, chart_dir: Path) -> list[dict]:
    """Generate per-stage charts for the feature selection pipeline."""
    chart_dir.mkdir(parents=True, exist_ok=True)
    charts = []
    scored = {col: s for col, s in report.scores.items() if s.get("shap") is not None}

    # --- Stage 1: Cheap prune waterfall ---
    s1 = next((s for s in report.stage_summaries if s["stage"] == 1), None)
    if s1:
        fig, ax = plt.subplots(figsize=(6, 3))
        bars = ax.bar(["Input", "Dropped", "Survivors"],
                      [s1["input_cols"], s1["dropped"], s1["survivors"]],
                      color=["#2196F3", "#F44336", "#4CAF50"])
        ax.bar_label(bars, fontsize=10)
        ax.set_title("S1: Cheap Prune (missingness, variance, ID-like)")
        ax.set_ylabel("Columns")
        plt.tight_layout()
        _save_chart(fig, chart_dir / "s1_cheap_prune.png")
        charts.append({"filename": "s1_cheap_prune.png", "description": f"Stage 1: {s1['input_cols']}→{s1['survivors']} cols"})

    # --- Stage 2: Dendrogram + correlation cluster heatmap ---
    Z = report.intermediates.get("linkage")
    corr_cols = report.intermediates.get("corr_columns", [])
    cluster_labels = report.intermediates.get("cluster_labels", {})
    clusters = report.intermediates.get("clusters", {})

    if Z is not None and len(corr_cols) > 1:
        from scipy.cluster.hierarchy import dendrogram

        # Dendrogram
        fig, ax = plt.subplots(figsize=(10, max(5, len(corr_cols) * 0.3)))
        dendrogram(Z, labels=corr_cols, orientation="left", ax=ax,
                   color_threshold=0.15, leaf_font_size=8)
        ax.set_xlabel("Distance (1 - |correlation|)")
        ax.set_title("S2: Correlation Clustering Dendrogram")
        ax.axvline(x=0.15, color="#D04030", linestyle="--", alpha=0.7, label="threshold=0.85")
        ax.legend(fontsize=8)
        plt.tight_layout()
        _save_chart(fig, chart_dir / "s2_dendrogram.png")
        charts.append({"filename": "s2_dendrogram.png", "description": "Stage 2: hierarchical clustering dendrogram"})

        # Cluster membership table (as chart)
        if clusters:
            multi_clusters = {k: v for k, v in clusters.items() if len(v) > 1}
            if multi_clusters:
                fig, ax = plt.subplots(figsize=(8, max(3, len(multi_clusters) * 0.8)))
                ax.axis("off")
                rows = []
                for label, cols in sorted(multi_clusters.items()):
                    dropped_in = [c for c in cols if any(d["column"] == c for d in report.dropped)]
                    kept_in = [c for c in cols if c not in dropped_in]
                    rows.append([f"Cluster {label}",
                                 ", ".join(kept_in) if kept_in else "—",
                                 ", ".join(dropped_in) if dropped_in else "—"])
                table = ax.table(cellText=rows,
                                 colLabels=["Cluster", "Kept (representative)", "Dropped (redundant)"],
                                 loc="center", cellLoc="left")
                table.auto_set_font_size(False)
                table.set_fontsize(8)
                table.scale(1, 1.5)
                ax.set_title("S2: Correlation Cluster Decisions", fontsize=11, pad=20)
                plt.tight_layout()
                _save_chart(fig, chart_dir / "s2_cluster_decisions.png")
                charts.append({"filename": "s2_cluster_decisions.png", "description": "Stage 2: cluster membership and drop decisions"})

    # --- Stage 3: Pseudo-target predictability ---
    predictability = report.intermediates.get("predictability", {})
    if predictability:
        sorted_pred = sorted(predictability.items(), key=lambda x: x[1], reverse=True)
        cols_p, vals_p = zip(*sorted_pred)
        fig, ax = plt.subplots(figsize=(8, max(4, len(cols_p) * 0.35)))
        colors = ["#F44336" if v > 0.95 else "#FFC107" if v > 0.8 else "#4CAF50" for v in vals_p]
        ax.barh(range(len(cols_p)), vals_p, color=colors)
        ax.set_yticks(range(len(cols_p)))
        ax.set_yticklabels(cols_p, fontsize=8)
        ax.invert_yaxis()
        ax.axvline(x=0.95, color="#D04030", linestyle="--", alpha=0.7, label="redundancy threshold")
        ax.set_xlabel("R² (predictability from other features)")
        ax.set_title("S3: Pseudo-Target Redundancy")
        ax.legend(fontsize=8)
        plt.tight_layout()
        _save_chart(fig, chart_dir / "s3_pseudo_target.png")
        charts.append({"filename": "s3_pseudo_target.png", "description": "Stage 3: per-column redundancy (R² from others)"})

    # --- Stage 4: MI + correlation scoring ---
    mi_data = {col: s.get("mutual_info") for col, s in report.scores.items() if s.get("mutual_info") is not None}
    corr_data = {col: s.get("target_corr") for col, s in report.scores.items() if s.get("target_corr") is not None}
    if mi_data and corr_data:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, max(4, len(mi_data) * 0.35)))

        # MI
        sorted_mi = sorted(mi_data.items(), key=lambda x: x[1], reverse=True)
        cols_m, vals_m = zip(*sorted_mi)
        ax1.barh(range(len(cols_m)), vals_m, color="#4CAF50", alpha=0.8)
        ax1.set_yticks(range(len(cols_m)))
        ax1.set_yticklabels(cols_m, fontsize=8)
        ax1.invert_yaxis()
        ax1.set_xlabel("Mutual Information")
        ax1.set_title("S4: Mutual Information with Target")

        # Correlation
        sorted_corr = sorted(corr_data.items(), key=lambda x: x[1], reverse=True)
        cols_c, vals_c = zip(*sorted_corr)
        ax2.barh(range(len(cols_c)), vals_c, color="#FF9800", alpha=0.8)
        ax2.set_yticks(range(len(cols_c)))
        ax2.set_yticklabels(cols_c, fontsize=8)
        ax2.invert_yaxis()
        ax2.set_xlabel("|Correlation| with Target")
        ax2.set_title("S4: Target Correlation")

        plt.tight_layout()
        _save_chart(fig, chart_dir / "s4_light_scoring.png")
        charts.append({"filename": "s4_light_scoring.png", "description": "Stage 4: MI and correlation with target"})

    # --- Stage 5: SHAP importance ---
    if scored:
        shap_data = {col: s["shap"] for col, s in scored.items() if s.get("shap")}
        if shap_data:
            shap_sorted = sorted(shap_data.items(), key=lambda x: x[1], reverse=True)
            cols_s, vals_s = zip(*shap_sorted)
            fig, ax = plt.subplots(figsize=(10, max(4, len(cols_s) * 0.4)))
            ax.barh(range(len(cols_s)), vals_s, color="#2196F3")
            ax.set_yticks(range(len(cols_s)))
            ax.set_yticklabels(cols_s, fontsize=9)
            ax.invert_yaxis()
            ax.set_xlabel("Mean |SHAP value|")
            ax.set_title("S5: SHAP Feature Importance (LightGBM)")
            plt.tight_layout()
            _save_chart(fig, chart_dir / "s5_shap_importance.png")
            charts.append({"filename": "s5_shap_importance.png", "description": "Stage 5: SHAP feature importance"})

    # --- Stage 6: Chart-retained columns ---
    if report.chart_retained:
        fig, ax = plt.subplots(figsize=(6, max(2, len(report.chart_retained) * 0.5)))
        ax.axis("off")
        rows = [[c["column"], c["reason"]] for c in report.chart_retained]
        table = ax.table(cellText=rows, colLabels=["Column", "Reason Retained"],
                         loc="center", cellLoc="left")
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.5)
        ax.set_title("S6: Chart-Retained Columns", fontsize=11, pad=20)
        plt.tight_layout()
        _save_chart(fig, chart_dir / "s6_chart_filter.png")
        charts.append({"filename": "s6_chart_filter.png", "description": "Stage 6: columns retained for charting"})

    # --- Overall pipeline sankey-like waterfall ---
    stage_names = {1: "Cheap\nPrune", 2: "Corr\nCluster", 3: "Pseudo\nTarget",
                   4: "Light\nScoring", 5: "SHAP", 6: "Chart\nFilter"}
    survivors_flow = []
    for s in report.stage_summaries:
        if "survivors" in s:
            survivors_flow.append((s["stage"], s.get("survivors", 0)))
    if survivors_flow:
        stages_x, vals_flow = zip(*survivors_flow)
        fig, ax = plt.subplots(figsize=(8, 4))
        colors_flow = ["#4CAF50" if i == 0 or vals_flow[i] == vals_flow[i-1]
                        else "#F44336" for i in range(len(vals_flow))]
        bars = ax.bar([stage_names.get(s, f"S{s}") for s in stages_x], vals_flow, color=colors_flow, alpha=0.8)
        ax.bar_label(bars, fontsize=10)
        ax.set_ylabel("Surviving Columns")
        ax.set_title(f"Feature Selection Pipeline: {vals_flow[0]} → {vals_flow[-1]} columns")
        plt.tight_layout()
        _save_chart(fig, chart_dir / "pipeline_waterfall.png")
        charts.append({"filename": "pipeline_waterfall.png", "description": f"Pipeline waterfall: {vals_flow[0]}→{vals_flow[-1]} cols"})

    # --- Correlation heatmap of final survivors ---
    numeric_survivors = [c for c in report.kept if pd.api.types.is_numeric_dtype(df[c])]
    if len(numeric_survivors) >= 2:
        corr = df[numeric_survivors].corr()
        fig, ax = plt.subplots(figsize=(max(8, len(numeric_survivors) * 0.6),
                                         max(6, len(numeric_survivors) * 0.5)))
        im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(numeric_survivors)))
        ax.set_xticklabels(numeric_survivors, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(numeric_survivors)))
        ax.set_yticklabels(numeric_survivors, fontsize=8)
        plt.colorbar(im, ax=ax, shrink=0.8)
        ax.set_title("Correlation Matrix (Final Survivors)")
        plt.tight_layout()
        _save_chart(fig, chart_dir / "correlation_survivors.png")
        charts.append({"filename": "correlation_survivors.png", "description": "Correlation heatmap of final surviving features"})

    return charts


def select_features(dataset_id: str, target_col: str | None = None,
                     run_shap: bool = True) -> dict:
    """Run the full feature selection pipeline."""
    steps = []
    conn = get_conn()
    run_id = make_run_id()

    # 1. Prerequisites
    ds = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    if not ds:
        raise RuntimeError(f"Dataset {dataset_id} not found.")

    # 2. Load data and replay pipeline
    print(f"Loading data and replaying engineer pipeline...")
    df, pipeline_summary, step_count = load_pipeline_and_run(dataset_id)
    print(f"  {len(df)} rows, {len(df.columns)} cols after {step_count} pipeline steps")
    steps.append({"name": "load_and_replay_pipeline",
                   "detail": f"{len(df)} rows, {len(df.columns)} cols, {step_count} steps"})

    # 3. Determine target
    human_notes = load_human_notes(dataset_id)
    if not target_col:
        target_col = guess_target(df, human_notes)
    if target_col:
        print(f"  Target predictor: {target_col}")
    else:
        print(f"  No target predictor identified (unsupervised selection)")
    steps.append({"name": "identify_target", "detail": target_col or "none"})

    # 4. Run staged selection
    print(f"\nRunning staged feature selection...")
    report = run_selection_pipeline(df, target_col=target_col, run_shap=run_shap)

    for s in report.stage_summaries:
        stage_name = s.get("name", "?")
        dropped = s.get("dropped", 0)
        survivors = s.get("survivors", "?")
        print(f"  Stage {s['stage']} ({stage_name}): dropped {dropped} → {survivors} survivors")
        steps.append({"name": f"stage_{s['stage']}_{stage_name}",
                       "detail": f"dropped {dropped}, {survivors} surviving"})

    print(f"\n  Total: {len(df.columns)} → {len(report.kept)} columns survived")
    print(f"  Dropped: {len(report.dropped)} columns")
    print(f"  Chart-retained: {len(report.chart_retained)} columns")

    # 5. LLM review
    print(f"\nAsking LLM to review selection...")
    meta = fetch_metadata(dataset_id)
    prompt_template = load_prompt(PROMPT_NAME)
    report_sections = format_report_for_llm(report)

    # Load column assessment from eda phase
    lv1_dir = ARTIFACTS_DIR / dataset_id / EDA_DIR
    column_assessment_text = ""
    if lv1_dir.exists():
        lv1_runs = sorted([d for d in lv1_dir.iterdir() if d.is_dir() and d.name.startswith("run-")])
        if lv1_runs:
            ca_path = lv1_runs[-1] / "tables" / "column_assessment.csv"
            if ca_path.exists():
                column_assessment_text = ca_path.read_text()

    task_type = "classify" if target_col and df[target_col].nunique() <= 20 else "regress"

    prompt = Template(prompt_template).safe_substitute(
        title=meta["name"],
        target_col=target_col or "(none — unsupervised)",
        task_type=task_type,
        col_count=len(df.columns),
        columns=", ".join(df.columns.tolist()),
        stage_summaries=report_sections["stage_summaries"],
        dropped_columns=report_sections["dropped_columns"],
        scored_columns=report_sections["scored_columns"],
        chart_retained=report_sections["chart_retained"],
        pipeline_step_count=step_count,
        pipeline_summary=pipeline_summary,
        human_notes=human_notes or "_(none)_",
    )

    llm_review = call_llm_json(prompt, max_tokens=2048)
    print(f"  LLM verdict: {llm_review.get('verdict', '?')}")
    steps.append({"name": "llm_review", "detail": f"verdict: {llm_review.get('verdict', '?')}"})

    # 6. Save outputs into run dir
    run_dir = get_run_dir(dataset_id, run_id)

    # Feature report (full machine-readable output)
    feature_report = {
        "dataset_id": dataset_id,
        "target_col": target_col,
        "task_type": task_type,
        "total_columns": len(df.columns),
        "selection_report": report.summary(),
        "llm_review": llm_review,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report_path = run_dir / "feature_report.json"
    report_path.write_text(json.dumps(feature_report, indent=2, default=str))
    print(f"  Feature report: {report_path}")

    # Scores table as CSV
    if report.scores:
        scores_df = pd.DataFrame.from_dict(report.scores, orient="index")
        scores_df.index.name = "column"
        scores_path = run_dir / "feature_scores.csv"
        scores_df.to_csv(scores_path)
        print(f"  Scores table: {scores_path}")

    # 6b. Charts
    chart_dir = run_dir / "charts"
    print("  Generating selection charts...")
    chart_results = generate_selection_charts(df, report, target_col, chart_dir)
    print(f"  {len(chart_results)} charts generated")
    steps.append({"name": "generate_charts", "detail": f"{len(chart_results)} charts"})

    # 7. Record in DB
    combined = {**llm_review, "selection_stages": report.stage_summaries}
    conn.execute(
        """INSERT INTO runs
           (id, dataset_id, action, action_code, agent, status, finished_at,
            prompt_template, llm_response, verdict, verdict_reason, artifact_paths)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id, dataset_id, ACTION, ACTION_CODE, "selector", "done",
            datetime.now(timezone.utc).isoformat(),
            PROMPT_NAME,
            json.dumps(combined),
            llm_review.get("verdict", "unknown"),
            llm_review.get("reason", ""),
            json.dumps([
                f"artifacts/{dataset_id}/{PHASE_DIR}/run-{run_id}/feature_report.json",
                f"artifacts/{dataset_id}/{PHASE_DIR}/run-{run_id}/{ACTION_CODE}-{ACTION}-{run_id}.md",
            ]),
        ),
    )
    conn.commit()
    conn.close()

    # 8. Write artifact into run dir
    artifact_path = write_run_artifact(
        run_id=run_id, dataset_id=dataset_id, action=ACTION, action_code=ACTION_CODE,
        agent="selector", model=DEFAULT_MODEL,
        title=f"{meta['name']} — feature selection",
        verdict=llm_review.get("verdict", "unknown"),
        steps=steps,
        prompt_text=prompt[:3000],
        llm_response=combined,
        context=f"Target: {target_col}\nPipeline: {step_count} steps\n"
                f"Selection: {len(df.columns)} → {len(report.kept)} columns",
        charts=chart_results, chart_subdir="charts",
        output_dir=run_dir,
    )
    ensure_human_notes(dataset_id, meta["name"])
    print(f"  Artifact: {artifact_path}")

    # Set flags
    if target_col:
        set_flag(dataset_id, "target_identified", run_id=run_id,
                 detail=f"{target_col} ({task_type})")
    if llm_review.get("final_keep"):
        set_flag(dataset_id, "features_selected", run_id=run_id,
                 detail=f"{len(llm_review['final_keep'])} features")
    if llm_review.get("overrides"):
        restored = [o for o in llm_review["overrides"] if o.get("action") == "restore"]
        if restored:
            set_flag(dataset_id, "structural_features_preserved", run_id=run_id,
                     detail=f"{len(restored)} features restored")

    # Append to session notebook
    try:
        nb = nb_lib.load_or_create(dataset_id)
        final_keep = as_str_list(llm_review.get("final_keep", []))
        nb_lib.add_phase_section(
            nb,
            action_code=ACTION_CODE,
            action=ACTION,
            verdict=llm_review.get("verdict", "?"),
            llm_narrative=(
                f"**Target:** `{target_col}`  \n"
                f"**Task type:** {task_type}  \n"
                f"**Selected features ({len(final_keep)}):** {', '.join(final_keep)}  \n"
                f"**Dropped:** {join_list(llm_review.get('drop', []))}  \n"
                f"**Structural preserved:** {join_list(llm_review.get('overrides', []), key='feature')}"
            ),
            code_cells=[
                # Show selected feature set
                f"# Selected features after 30-select\n"
                f"selected_features = {final_keep!r}\n"
                f"target_col = {target_col!r}\n"
                f"available = [f for f in selected_features if f in df.columns]\n"
                f"missing = [f for f in selected_features if f not in df.columns]\n"
                f"if missing: print(f'⚠ Missing: {{missing}}')\n"
                f"print(f'Features available: {{len(available)}}/{{len(selected_features)}}')\n"
                f"X = df[available]; y = df[target_col]\n"
                f"X.describe().T[['count','mean','std','min','max']]",

                # Feature-target correlation bar chart
                f"# Feature–target correlation\n"
                f"import matplotlib.pyplot as plt, pandas as pd\n"
                f"_num = [f for f in available if pd.api.types.is_numeric_dtype(df[f]) and f != target_col]\n"
                f"_corrs = df[_num].corrwith(df[target_col]).abs().sort_values(ascending=True)\n"
                f"fig, ax = plt.subplots(figsize=(8, max(4, len(_corrs) * 0.35)))\n"
                f"_corrs.plot.barh(ax=ax, color='steelblue', alpha=0.85)\n"
                f"ax.axvline(0.3, color='red', linestyle='--', alpha=0.5, label='|r|=0.3')\n"
                f"ax.set_xlabel('|Correlation with target|')\n"
                f"ax.set_title(f'Feature–Target Correlation — target: {{target_col}}')\n"
                f"ax.legend(); plt.tight_layout(); plt.show()",
            ],
        )
        nb_lib.save(nb, dataset_id)
        print(f"  Notebook updated: session.ipynb")
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"  Notebook write failed: {e}")

    return llm_review


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m agents.selector <dataset_id> [--target <col>] [--no-shap]")
        sys.exit(1)

    dataset_id = sys.argv[1]
    target_col = None
    run_shap = True

    args = sys.argv[2:]
    for i, arg in enumerate(args):
        if arg == "--target" and i + 1 < len(args):
            target_col = args[i + 1]
        elif arg == "--no-shap":
            run_shap = False

    result = select_features(dataset_id, target_col=target_col, run_shap=run_shap)
    print(f"\n=== Feature Selection Complete ===")
    print(f"Verdict: {result.get('verdict', '?')}")
    print(f"Reason:  {result.get('reason', '')}")
    if result.get("final_keep"):
        print(f"Final columns: {len(result['final_keep'])}")
    if result.get("overrides"):
        print(f"Overrides: {len(result['overrides'])}")


if __name__ == "__main__":
    main()
