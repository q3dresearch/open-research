#!/usr/bin/env python3
"""
Phase 25 Clusterer — unsupervised regime discovery.

Runs multi-view clustering (GMM, KPrototypes, UMAP+HDBSCAN) to find
natural clusters, then validates whether they define genuine regimes
(different slopes) vs mere level differences (different intercepts).

Produces cluster_label as a Track B structural feature for downstream
phases (select, report).

Target column must be specified via --target flag, human-notes, or
prior phase artifacts. No guessing.

Usage:
    python -m agents.clusterer <dataset_id> --target <col>
"""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from lib.db import RunContext, init_db
from lib.ckan import fetch_metadata, DATA_DIR
from lib.eda import basic_profile, format_profile
from lib.eda.clustering import (
    multi_view_cluster, cluster_profile, cluster_quality_report,
    silhouette_analysis, validate_cluster_sizes,
)
from lib.llm import load_prompt, call_llm_json, DEFAULT_MODEL
from lib.artifacts import (
    write_run_artifact, ensure_human_notes, load_human_notes,
    load_prior_artifacts, ARTIFACTS_DIR, ACTION_CODES, action_dir,
)
from lib.flags import set_flag
from lib import notebook as nb_lib
from lib.llm_parse import as_str_list, join_list

ACTION = "cluster"
ACTION_CODE = ACTION_CODES[ACTION]
PHASE_DIR = action_dir(ACTION_CODE, ACTION)
PROMPT_NAME = f"research-{ACTION_CODE}-{ACTION}"

# References to upstream phases
CLEAN_CODE = ACTION_CODES["clean"]
CLEAN_DIR = action_dir(CLEAN_CODE, "clean")
ENGINEER_CODE = ACTION_CODES["engineer"]
ENGINEER_DIR = action_dir(ENGINEER_CODE, "engineer")
EDA_CODE = ACTION_CODES["eda"]
EDA_DIR = action_dir(EDA_CODE, "eda")
SELECT_CODE = ACTION_CODES["select"]
SELECT_DIR = action_dir(SELECT_CODE, "select")


def get_phase_dir(dataset_id: str) -> Path:
    d = ARTIFACTS_DIR / dataset_id / PHASE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_run_dir(dataset_id: str, run_id: str) -> Path:
    d = get_phase_dir(dataset_id) / f"run-{run_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_and_replay(dataset_id: str) -> tuple[pd.DataFrame, str]:
    """Load raw CSV, replay clean + engineer pipelines. Returns (df, summary)."""
    csv_path = DATA_DIR / f"{dataset_id}.csv"
    if not csv_path.exists():
        raise RuntimeError(f"No data file at {csv_path}.")

    raw_df = pd.read_csv(csv_path)
    df = raw_df.copy()
    summary_parts = [f"raw: {len(df)} rows, {len(df.columns)} cols"]

    # Replay clean pipeline if exists
    clean_pipeline_path = ARTIFACTS_DIR / dataset_id / CLEAN_DIR / "clean_pipeline.py"
    if clean_pipeline_path.exists():
        spec = importlib.util.spec_from_file_location("clean_pipeline", clean_pipeline_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        df = mod.run_pipeline(df)
        summary_parts.append(f"after clean: {len(df.columns)} cols")
        print(f"  Replayed clean pipeline: {len(df)} rows, {len(df.columns)} cols")

    # Replay engineer pipeline if exists
    eng_pipeline_path = ARTIFACTS_DIR / dataset_id / ENGINEER_DIR / "pipeline.py"
    if eng_pipeline_path.exists():
        spec = importlib.util.spec_from_file_location("pipeline", eng_pipeline_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        df = mod.run_pipeline(df)
        summary_parts.append(f"after engineer: {len(df.columns)} cols")
        print(f"  Replayed engineer pipeline: {len(df)} rows, {len(df.columns)} cols")

    return df, " → ".join(summary_parts)


def resolve_target(dataset_id: str, cli_target: str | None,
                   human_notes: str | None) -> str | None:
    """Resolve target column from explicit sources only — no guessing.

    Priority:
      1. CLI --target flag (user explicitly specified)
      2. Human-notes (look for "target: <col>" pattern)
      3. Prior select phase feature_report.json (LLM already judged it)

    Returns None if no source provides a target.
    """
    # 1. CLI flag
    if cli_target:
        return cli_target

    # 2. Human-notes explicit target declaration
    if human_notes:
        import re
        match = re.search(r'(?:target|predict|y_col)\s*[:=]\s*(\S+)', human_notes, re.IGNORECASE)
        if match:
            return match.group(1).strip('`"\'')

    # 3. Prior select phase (LLM already identified it)
    select_dir = ARTIFACTS_DIR / dataset_id / SELECT_DIR
    if select_dir.exists():
        runs = sorted([d for d in select_dir.iterdir() if d.is_dir() and d.name.startswith("run-")])
        if runs:
            report_path = runs[-1] / "feature_report.json"
            if report_path.exists():
                report = json.loads(report_path.read_text())
                t = report.get("target_col")
                if t:
                    return t

    # 4. Prior engineer runs (LLM may have mentioned target in response)
    conn = init_db()
    row = conn.execute(
        """SELECT llm_response FROM runs
           WHERE dataset_id = ? AND action = 'eda'
           ORDER BY finished_at DESC LIMIT 1""",
        (dataset_id,),
    ).fetchone()
    conn.close()
    if row and row["llm_response"]:
        try:
            resp = json.loads(row["llm_response"])
            t = resp.get("target_col") or resp.get("target")
            if t:
                return t
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def select_cluster_features(df: pd.DataFrame, target_col: str | None) -> list[str]:
    """Pick numeric features suitable for clustering (exclude target, IDs, flags)."""
    numeric = df.select_dtypes(include="number").columns.tolist()
    exclude_patterns = ["_id", "_flag", "is_outlier", "index"]
    features = []
    for c in numeric:
        if c == target_col:
            continue
        if any(p in c.lower() for p in exclude_patterns):
            continue
        if df[c].nunique() <= 1:
            continue
        features.append(c)
    return features


def _save_chart(fig, path):
    fig.savefig(path, dpi=120, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def _cluster_palette(n: int) -> list:
    return [plt.cm.Set2(i / max(n - 1, 1)) for i in range(n)]


def generate_cluster_histograms(
    df: pd.DataFrame,
    labels: np.ndarray,
    feature_cols: list[str],
    chart_dir: Path,
    cluster_names: dict | None = None,
) -> list[dict]:
    """A4-paginated histograms: each numeric feature colored by cluster.

    Layout: 2 columns × 4 rows = 8 features per page.
    Returns list of chart metadata dicts.
    """
    chart_dir.mkdir(parents=True, exist_ok=True)
    charts = []

    temp = df[feature_cols].copy()
    temp["_cluster"] = labels
    temp = temp[temp["_cluster"] >= 0]
    clusters = sorted(temp["_cluster"].unique())
    palette = _cluster_palette(len(clusters))

    COLS, ROWS = 2, 4
    PER_PAGE = COLS * ROWS
    A4 = (8.27, 11.69)

    pages = [feature_cols[i: i + PER_PAGE] for i in range(0, len(feature_cols), PER_PAGE)]

    for page_idx, page_features in enumerate(pages):
        n = len(page_features)
        fig, axes = plt.subplots(ROWS, COLS, figsize=A4)
        axes_flat = axes.flatten()

        for ax_idx, feat in enumerate(page_features):
            ax = axes_flat[ax_idx]
            for cl, color in zip(clusters, palette):
                data = temp[temp["_cluster"] == cl][feat].dropna()
                label = cluster_names.get(str(cl), f"C{cl}") if cluster_names else f"C{cl}"
                ax.hist(data, bins=40, alpha=0.55, color=color, label=f"{label} (n={len(data):,})")
            ax.set_title(feat, fontsize=9)
            ax.tick_params(labelsize=7)
            ax.legend(fontsize=6, framealpha=0.6)

        # Hide unused axes on last page
        for ax_idx in range(n, len(axes_flat)):
            axes_flat[ax_idx].set_visible(False)

        fig.suptitle(
            f"Feature Distributions by Cluster  —  page {page_idx + 1}/{len(pages)}",
            fontsize=11, y=1.01,
        )
        plt.tight_layout()
        fname = f"histograms_p{page_idx + 1:02d}.png"
        _save_chart(fig, chart_dir / fname)
        charts.append({
            "filename": fname,
            "description": (
                f"Histograms page {page_idx + 1}: "
                f"{', '.join(page_features[:4])}{'...' if len(page_features) > 4 else ''}"
            ),
        })

    return charts


def generate_cluster_radar(
    df: pd.DataFrame,
    labels: np.ndarray,
    feature_cols: list[str],
    chart_dir: Path,
    cluster_names: dict | None = None,
) -> dict | None:
    """Radar chart: standardized numeric means stacked by cluster.

    Each cluster becomes one filled polygon.  Axes = features (standardized
    so all features are on the same scale).  Useful for quick visual sweep of
    which cluster is "high" or "low" across dimensions.
    """
    import math
    from sklearn.preprocessing import StandardScaler

    chart_dir.mkdir(parents=True, exist_ok=True)

    temp = df[feature_cols].copy()
    temp["_cluster"] = labels
    temp = temp[temp["_cluster"] >= 0]

    # Standardize features
    scaler = StandardScaler()
    temp[feature_cols] = scaler.fit_transform(temp[feature_cols])

    # Cluster means
    cluster_means = temp.groupby("_cluster")[feature_cols].mean()
    clusters = cluster_means.index.tolist()
    palette = _cluster_palette(len(clusters))

    n_feats = len(feature_cols)
    if n_feats < 3:
        return None

    # Angles: evenly spaced around the circle, closed
    angles = [2 * math.pi * i / n_feats for i in range(n_feats)]
    angles += angles[:1]  # close the polygon

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"polar": True})

    for cl, color in zip(clusters, palette):
        values = cluster_means.loc[cl, feature_cols].tolist()
        values += values[:1]  # close
        label = cluster_names.get(str(cl), f"C{cl}") if cluster_names else f"C{cl}"
        ax.plot(angles, values, color=color, linewidth=1.5, label=label)
        ax.fill(angles, values, color=color, alpha=0.20)

    ax.set_thetagrids(
        [a * 180 / math.pi for a in angles[:-1]],
        labels=feature_cols,
        fontsize=8,
    )
    ax.set_title("Cluster Profiles — Standardized Feature Means", pad=20, fontsize=11)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.15), fontsize=9)
    ax.tick_params(labelsize=7)
    plt.tight_layout()

    fname = "radar_cluster_profiles.png"
    _save_chart(fig, chart_dir / fname)
    return {
        "filename": fname,
        "description": f"Radar chart: standardized cluster means across {n_feats} features",
    }


def generate_cluster_charts(df: pd.DataFrame, views: list[dict],
                            best_labels: np.ndarray, target_col: str | None,
                            chart_dir: Path,
                            feature_cols: list[str] | None = None,
                            cluster_names: dict | None = None) -> list[dict]:
    """Generate clustering charts for the artifact."""
    chart_dir.mkdir(parents=True, exist_ok=True)
    charts = []

    # 1. Silhouette comparison across views
    if len(views) >= 2:
        fig, ax = plt.subplots(figsize=(8, 4))
        methods = [v["method"] for v in views]
        sils = [v["silhouette"] for v in views]
        colors = ["#4CAF50" if s > 0.3 else "#FFC107" if s > 0.15 else "#F44336" for s in sils]
        bars = ax.bar(methods, sils, color=colors)
        ax.bar_label(bars, fmt="%.3f", fontsize=10)
        ax.axhline(y=0.3, color="#888", linestyle="--", alpha=0.5, label="threshold=0.3")
        ax.set_ylabel("Silhouette Score")
        ax.set_title("Multi-View Clustering Comparison")
        ax.legend(fontsize=8)
        plt.tight_layout()
        _save_chart(fig, chart_dir / "view_comparison.png")
        charts.append({"filename": "view_comparison.png",
                        "description": f"Multi-view silhouette comparison: {', '.join(methods)}"})

    # 2. Cluster size distribution (best view)
    unique, counts = np.unique(best_labels[best_labels >= 0], return_counts=True)
    if len(unique) >= 2:
        fig, ax = plt.subplots(figsize=(6, 4))
        colors = _cluster_palette(len(unique))
        bars = ax.bar([f"C{u}" for u in unique], counts, color=colors)
        ax.bar_label(bars, fontsize=9)
        ax.set_ylabel("Count")
        ax.set_title("Cluster Sizes (Best View)")
        pcts = [f"C{u}: {c/len(best_labels):.1%}" for u, c in zip(unique, counts)]
        ax.set_xlabel(", ".join(pcts))
        plt.tight_layout()
        _save_chart(fig, chart_dir / "cluster_sizes.png")
        charts.append({"filename": "cluster_sizes.png",
                        "description": f"Cluster sizes: {len(unique)} clusters"})

    # 3. Target distribution by cluster
    if target_col and target_col in df.columns:
        temp = df.copy()
        temp["_cluster"] = best_labels
        temp = temp[temp["_cluster"] >= 0]
        fig, ax = plt.subplots(figsize=(8, 5))
        clusters = sorted(temp["_cluster"].unique())
        for cl, color in zip(clusters, _cluster_palette(len(clusters))):
            data = temp[temp["_cluster"] == cl][target_col].dropna()
            label = cluster_names.get(str(cl), f"C{cl}") if cluster_names else f"C{cl}"
            ax.hist(data, bins=50, alpha=0.5, color=color, label=f"{label} (n={len(data):,})")
        ax.set_xlabel(target_col)
        ax.set_ylabel("Count")
        ax.set_title(f"{target_col} Distribution by Cluster")
        ax.legend(fontsize=8)
        plt.tight_layout()
        _save_chart(fig, chart_dir / "target_by_cluster.png")
        charts.append({"filename": "target_by_cluster.png",
                        "description": f"{target_col} distribution by cluster"})

    # 4. Per-feature histograms (A4 paginated, 2 col × 4 row)
    if feature_cols:
        hist_charts = generate_cluster_histograms(df, best_labels, feature_cols,
                                                   chart_dir, cluster_names)
        charts.extend(hist_charts)

    # 5. Radar chart (standardized cluster profiles)
    if feature_cols and len(feature_cols) >= 3:
        radar = generate_cluster_radar(df, best_labels, feature_cols, chart_dir, cluster_names)
        if radar:
            charts.append(radar)

    return charts


def format_views_for_prompt(views: list[dict]) -> tuple[str, str]:
    """Format multi-view results for the LLM prompt. Returns (comparison, best_details)."""
    comparison_lines = []
    for v in views:
        info = v.get("info", {})
        comparison_lines.append(
            f"**{v['method']}**: k={v['n_clusters']}, silhouette={v['silhouette']}"
            f"\n  Strengths: {info.get('strengths', '?')}"
            f"\n  Weaknesses: {info.get('weaknesses', '?')}"
        )
        if "noise_pct" in info:
            comparison_lines[-1] += f"\n  Noise: {info['noise_pct']:.1%} unassigned"

    best = views[0] if views else None
    best_details = "(no views available)"
    if best:
        best_details = f"Method: {best['method']}, k={best['n_clusters']}, silhouette={best['silhouette']}"

    return "\n\n".join(comparison_lines), best_details


def run_cluster(dataset_id: str, target_col: str | None = None) -> dict:
    """Run the full clustering pipeline."""
    audit_steps = []
    ctx = RunContext(dataset_id, ACTION, ACTION_CODE, "clusterer")
    conn = ctx.conn
    run_id = ctx.run_id

    # 1. Prerequisites
    ds = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    if not ds:
        raise RuntimeError(f"Dataset {dataset_id} not found.")

    # 2. Load data and replay pipelines
    print("Loading data and replaying clean + engineer pipelines...")
    df, replay_summary = load_and_replay(dataset_id)
    print(f"  {replay_summary}")
    audit_steps.append({"name": "load_and_replay", "detail": replay_summary})

    # 3. Resolve target (no guessing — explicit sources only)
    human_notes = load_human_notes(dataset_id)
    target_col = resolve_target(dataset_id, target_col, human_notes)
    if target_col and target_col not in df.columns:
        print(f"  WARNING: resolved target '{target_col}' not in dataframe columns. Clearing.")
        target_col = None
    if not target_col:
        print("  No target column resolved. Regime validation will be skipped.")
        print("  Hint: specify --target <col> or add 'target: <col>' to human-notes.md")
    else:
        print(f"  Target: {target_col}")
    audit_steps.append({"name": "resolve_target", "detail": target_col or "none (regime validation skipped)"})

    # 4. Select features for clustering
    cluster_features = select_cluster_features(df, target_col)
    print(f"  Clustering on {len(cluster_features)} numeric features")
    audit_steps.append({"name": "select_features",
                         "detail": f"{len(cluster_features)} features: {', '.join(cluster_features[:10])}"})

    if len(cluster_features) < 2:
        print("  Not enough numeric features for clustering. Skipping.")
        conn.close()
        return {"verdict": "fail", "reason": "fewer than 2 numeric features available"}

    # 5. Run multi-view clustering
    print("\nRunning multi-view clustering...")
    cluster_df = df[cluster_features].copy()
    views = multi_view_cluster(cluster_df, max_k=6, target_col=target_col)

    for v in views:
        print(f"  {v['method']}: k={v['n_clusters']}, silhouette={v['silhouette']}")
    audit_steps.append({"name": "multi_view_cluster",
                         "detail": f"{len(views)} views: " +
                         ", ".join(f"{v['method']}(sil={v['silhouette']})" for v in views)})

    if not views:
        print("  No clustering views produced. Skipping.")
        conn.close()
        return {"verdict": "fail", "reason": "all clustering methods failed"}

    # 6. Quality report on best view
    best_view = views[0]
    best_labels = best_view["labels"]
    print(f"\nBest view: {best_view['method']} (silhouette={best_view['silhouette']})")

    # Cluster profiles
    temp_df = df.copy()
    temp_df["cluster_label"] = best_labels
    temp_clean = temp_df[temp_df["cluster_label"] >= 0]
    profiles = cluster_profile(temp_clean, "cluster_label")
    print(f"  Cluster profiles computed")

    # Regime validation (only if target is known)
    quality_report = None
    if target_col:
        non_noise = temp_clean.index
        quality_report = cluster_quality_report(
            df.loc[non_noise], best_labels[best_labels >= 0],
            target_col, cluster_features,
            silhouette=best_view["silhouette"],
        )
        n_regime = quality_report["n_regime_features"]
        sil = best_view["silhouette"]
        sil_flag = "" if sil >= 0.3 else f" ⚠ silhouette={sil:.3f}<0.3"
        print(f"  Quality: {quality_report['verdict']}, "
              f"{n_regime}/{quality_report['n_features_tested']} regime features, "
              f"ANOVA p={quality_report['anova']['p_value']}{sil_flag}")
        audit_steps.append({"name": "quality_report",
                             "detail": f"{quality_report['verdict']}: {n_regime} regime features, sil={sil:.3f}"})

    # 7. Charts
    run_dir = get_run_dir(dataset_id, run_id)
    chart_dir = run_dir / "charts"
    print("  Generating charts...")
    chart_results = generate_cluster_charts(
        df, views, best_labels, target_col, chart_dir,
        feature_cols=cluster_features,
        cluster_names=None,  # updated below after LLM names clusters
    )
    audit_steps.append({"name": "generate_charts", "detail": f"{len(chart_results)} charts"})

    # 8. LLM review
    print("\nAsking LLM to review clustering results...")
    meta = fetch_metadata(dataset_id)
    prior_context = load_prior_artifacts(dataset_id, before_action_code=ACTION_CODE)

    view_comparison, best_view_details = format_views_for_prompt(views)

    # Silhouette report
    sil_df = silhouette_analysis(cluster_df, max_k=6)
    sil_text = sil_df.to_string(index=False)

    # Format regime tests
    regime_text = "(no target — regime validation skipped)"
    anova_text = regime_text
    if quality_report:
        regime_lines = []
        for rt in quality_report["regime_tests"]:
            marker = "REGIME" if rt["is_regime"] else "level-only"
            regime_lines.append(
                f"  {rt['feature']}: slope_p={rt['slope_p']}, "
                f"intercept_p={rt['intercept_p']}, F={rt['f_stat']} [{marker}]"
            )
        regime_text = "\n".join(regime_lines) if regime_lines else "(no numeric features tested)"
        a = quality_report["anova"]
        anova_text = f"F={a['f_stat']}, p={a['p_value']}, η²={a['eta_squared']}"

    prompt_template = load_prompt(PROMPT_NAME)
    prompt = Template(prompt_template).safe_substitute(
        title=meta["name"],
        target_col=target_col or "(none — regime validation skipped)",
        cluster_features=", ".join(cluster_features[:20]),
        columns=", ".join(df.columns.tolist()),
        prior_context=prior_context[:3000] if prior_context else "_(no prior findings)_",
        view_comparison=view_comparison,
        best_view_details=best_view_details,
        cluster_profiles=profiles.to_string(),
        silhouette_report=sil_text,
        regime_tests=regime_text,
        anova_result=anova_text,
        human_notes=human_notes or "_(none)_",
    )

    llm_review = call_llm_json(prompt, max_tokens=2048)
    print(f"  LLM verdict: {llm_review.get('verdict', '?')}")
    audit_steps.append({"name": "llm_review", "detail": f"verdict: {llm_review.get('verdict', '?')}"})

    # 9. Save outputs
    if llm_review.get("add_to_pipeline", False):
        label_path = get_phase_dir(dataset_id) / "cluster_labels.csv"
        # Save with df's actual index so downstream can join correctly
        # even if row counts differ by ±1 due to non-deterministic deduplication
        # Save cluster_label as string ("C0", "C1", ...) so it loads as object dtype.
        # Integer labels would be treated as numeric by statsmodels OLS and sklearn,
        # implying a false ordinal relationship between clusters.
        name_map = llm_review.get("cluster_names", {})
        str_labels = [
            name_map.get(str(lbl), f"C{lbl}") if name_map else f"C{lbl}"
            for lbl in best_labels
        ]
        label_df = pd.DataFrame({"cluster_label": str_labels}, index=df.index)
        if name_map:
            label_df["cluster_name"] = label_df["cluster_label"]
        label_df.to_csv(label_path, index=True)  # index=True saves the df index
        print(f"  Saved cluster labels: {label_path}")

    # Save full report
    report = {
        "dataset_id": dataset_id,
        "target_col": target_col,
        "cluster_features": cluster_features,
        "views": [{k: v for k, v in view.items() if k != "labels"}
                   for view in views],
        "best_method": best_view["method"],
        "quality_report": quality_report,
        "llm_review": llm_review,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report_path = run_dir / "cluster_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))

    # 10. Record in DB
    combined = {**llm_review, "quality_report": quality_report}
    ctx.finish(
        verdict=llm_review.get("verdict", "unknown"),
        verdict_reason=llm_review.get("reason", ""),
        llm_response=json.dumps(combined, default=str),
        artifact_paths=[
            f"artifacts/{dataset_id}/{PHASE_DIR}/run-{run_id}/cluster_report.json",
            f"artifacts/{dataset_id}/{PHASE_DIR}/cluster_labels.csv",
        ],
        prompt_template=PROMPT_NAME,
    )
    conn.commit()
    ctx.close()

    # 11. Write artifact
    artifact_path = write_run_artifact(
        run_id=run_id, dataset_id=dataset_id, action=ACTION, action_code=ACTION_CODE,
        agent="clusterer", model=DEFAULT_MODEL,
        title=f"{meta['name']} — regime discovery",
        verdict=llm_review.get("verdict", "unknown"),
        steps=audit_steps,
        prompt_text=prompt[:3000],
        llm_response=combined,
        context=f"Target: {target_col}\nViews: {len(views)}\n"
                f"Best: {best_view['method']} (sil={best_view['silhouette']})",
        charts=chart_results, chart_subdir="charts",
        output_dir=run_dir,
    )
    ensure_human_notes(dataset_id, meta["name"])
    print(f"  Artifact: {artifact_path}")

    # Set flags
    verdict = llm_review.get("verdict", "fail")
    if verdict in ("pass", "marginal"):
        set_flag(dataset_id, "clusters_discovered", run_id=run_id,
                 detail=f"{best_view['method']}, k={best_view['n_clusters']}, sil={best_view['silhouette']}")
    if quality_report and quality_report.get("n_regime_features", 0) > 0:
        set_flag(dataset_id, "regime_validated", run_id=run_id,
                 detail=f"{quality_report['n_regime_features']} features with different slopes")
    if llm_review.get("add_to_pipeline", False):
        set_flag(dataset_id, "cluster_label_added", run_id=run_id)

    # 12. Append to session notebook
    try:
        nb = nb_lib.load_or_create(dataset_id)
        name_map = llm_review.get("cluster_names", {})
        cluster_names_str = json.dumps(name_map, indent=2) if name_map else "{}"
        nb_lib.add_phase_section(
            nb,
            action_code=ACTION_CODE,
            action=ACTION,
            verdict=verdict,
            llm_narrative=(
                f"**Chosen method:** {llm_review.get('chosen_method', best_view['method'])}  \n"
                f"**Reason:** {llm_review.get('reason', '')}  \n"
                f"**Regime features** (different slopes per cluster): "
                f"{join_list(llm_review.get('regime_features', []))}  \n"
                f"**Interaction candidates:** "
                f"{join_list(llm_review.get('interaction_candidates', []))}"
            ),
            code_cells=[
                # Attach cluster labels — index-join so row-count mismatches don't crash
                "# Attach cluster labels from 25-cluster output\n"
                "import pandas as pd\n"
                f"_labels = pd.read_csv(ARTIFACTS / '25-cluster/cluster_labels.csv', index_col=0)\n"
                "_label_cols = [c for c in _labels.columns if c in ('cluster_label', 'cluster_name')]\n"
                "df = df.join(_labels[_label_cols], how='left')\n"
                "df[_label_cols].value_counts().sort_index()",
                # Cluster names declared by LLM
                f"# LLM cluster name mapping\ncluster_names = {cluster_names_str}\ncluster_names",
                # Quick profile
                "df.groupby('cluster_label')[["
                + ", ".join(f'"{f}"' for f in cluster_features[:6])
                + "]].mean().round(3)",
            ],
        )
        # Cluster histograms — one page per 8 features (A4, 2×4)
        nb_lib.add_code_cell(nb,
            "import matplotlib.pyplot as plt\n"
            "_num_feats = [c for c in df.select_dtypes(include='number').columns if c != 'cluster_label']\n"
            "_page_size = 8\n"
            "for _ps in range(0, len(_num_feats), _page_size):\n"
            "    _pf = _num_feats[_ps:_ps + _page_size]\n"
            "    fig, axes = plt.subplots(4, 2, figsize=(8.27, 11.69))\n"
            "    for ax, col in zip(axes.flat, _pf):\n"
            "        for lbl, grp in df.groupby('cluster_label'):\n"
            "            grp[col].dropna().hist(bins=30, ax=ax, alpha=0.55, density=True, label=str(lbl))\n"
            "        ax.set_title(col, fontsize=9); ax.legend(fontsize=7)\n"
            "    for ax in axes.flat[len(_pf):]:\n"
            "        ax.set_visible(False)\n"
            "    plt.suptitle(f'Cluster Distributions (features {_ps+1}–{_ps+len(_pf)})', fontsize=11)\n"
            "    plt.tight_layout(); plt.show()"
        )
        # Cluster radar chart
        nb_lib.add_code_cell(nb,
            "import matplotlib.pyplot as plt, numpy as np, pandas as pd\n"
            "from sklearn.preprocessing import StandardScaler\n"
            "_feats = [c for c in df.select_dtypes(include='number').columns\n"
            "          if c != 'cluster_label' and df[c].std() > 0][:10]\n"
            "_df_s = df[_feats + ['cluster_label']].dropna()\n"
            "_scaler = StandardScaler()\n"
            "_scaled = pd.DataFrame(_scaler.fit_transform(_df_s[_feats]), columns=_feats, index=_df_s.index)\n"
            "_scaled['cluster_label'] = _df_s['cluster_label']\n"
            "_means = _scaled.groupby('cluster_label')[_feats].mean()\n"
            "_n = len(_feats)\n"
            "_angles = np.linspace(0, 2 * np.pi, _n, endpoint=False).tolist() + [0]\n"
            "fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))\n"
            "_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']\n"
            "for i, (lbl, row) in enumerate(_means.iterrows()):\n"
            "    _vals = row.tolist() + row[:1].tolist()\n"
            "    ax.plot(_angles, _vals, '-o', linewidth=2, color=_colors[i % 4], label=str(lbl))\n"
            "    ax.fill(_angles, _vals, alpha=0.1, color=_colors[i % 4])\n"
            "ax.set_xticks(_angles[:-1]); ax.set_xticklabels(_feats, size=8)\n"
            "ax.set_title('Cluster Profiles (standardised means)', pad=20)\n"
            "ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))\n"
            "plt.tight_layout(); plt.show()"
        )
        nb_lib.save(nb, dataset_id)
        print(f"  Notebook updated: session.ipynb")
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"  Notebook write failed: {e}")

    return llm_review


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m agents.clusterer <dataset_id> --target <col>")
        sys.exit(1)

    dataset_id = sys.argv[1]
    target_col = None

    args = sys.argv[2:]
    for i, arg in enumerate(args):
        if arg == "--target" and i + 1 < len(args):
            target_col = args[i + 1]

    result = run_cluster(dataset_id, target_col=target_col)
    print(f"\n=== Regime Discovery Complete ===")
    print(f"Verdict: {result.get('verdict', '?')}")
    print(f"Reason:  {result.get('reason', '')}")
    if result.get("chosen_method"):
        print(f"Method:  {result['chosen_method']}")
    if result.get("regime_features"):
        print(f"Regime features: {', '.join(result['regime_features'])}")


if __name__ == "__main__":
    main()
