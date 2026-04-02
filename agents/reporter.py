#!/usr/bin/env python3
"""
Level 4 Reporter — generates publication-ready research reports.

Gathers all artifacts from prior phases, endgame charts, and human notes,
then asks the LLM to produce a dual-layer markdown report:
  Layer 1: Narrative (consumer-readable)
  Layer 2: Audit trail (reproducible, in <details> blocks)

Usage:
    python -m agents.reporter <dataset_id>
"""

import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.db import RunContext
from lib.ckan import fetch_metadata, DATA_DIR
from lib.llm import load_prompt, call_llm, DEFAULT_MODEL
from lib.artifacts import (
    ensure_human_notes, load_human_notes, load_prior_artifacts, ARTIFACTS_DIR,
    ACTION_CODES, action_dir,
)
from lib.flags import set_flag
from lib import notebook as nb_lib

ACTION = "report"
ACTION_CODE = ACTION_CODES[ACTION]
PHASE_DIR = action_dir(ACTION_CODE, ACTION)
PROMPT_NAME = f"research-{ACTION_CODE}-{ACTION}"

# References to other phases
CLEAN_CODE = ACTION_CODES["clean"]
CLEAN_DIR = action_dir(CLEAN_CODE, "clean")
ENGINEER_DIR = action_dir(ACTION_CODES["engineer"], "engineer")
CLUSTER_CODE = ACTION_CODES["cluster"]
CLUSTER_DIR = action_dir(CLUSTER_CODE, "cluster")
SELECT_DIR = action_dir(ACTION_CODES["select"], "select")
EDA_DIR = action_dir(ACTION_CODES["eda"], "eda")

MAX_SAMPLE_RECORDS = 5
MAX_STEP_LOG_ENTRIES = 15
MAX_FINDINGS_CHARS = 3000


def get_run_dir(dataset_id: str, run_id: str) -> Path:
    d = ARTIFACTS_DIR / dataset_id / PHASE_DIR / f"run-{run_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state_json(dataset_id: str) -> dict | None:
    path = ARTIFACTS_DIR / dataset_id / ENGINEER_DIR / "state.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def load_feature_report(dataset_id: str) -> dict | None:
    """Load the most recent feature selection report."""
    lv3_dir = ARTIFACTS_DIR / dataset_id / SELECT_DIR
    if not lv3_dir.exists():
        return None
    runs = sorted([d for d in lv3_dir.iterdir() if d.is_dir() and d.name.startswith("run-")])
    if not runs:
        return None
    report_path = runs[-1] / "feature_report.json"
    if report_path.exists():
        return json.loads(report_path.read_text())
    return None


def build_column_glossary(dataset_id: str, meta: dict) -> list[dict]:
    """Assemble a column-level glossary from all pipeline artifacts.

    Each entry: {column, origin, how, intuition, selection_outcome, selection_reason}

    Sources:
    - Original columns: dataset metadata (meta["columns"])
    - Clean steps: 15-clean/state.json step_log (columns_affected per step)
    - Engineer steps: 20-engineer/pipeline.py docstrings parsed via ast
    - Selection: feature_report.json kept/dropped/overrides
    """
    import ast as _ast

    glossary: dict[str, dict] = {}

    # 1. Seed with original columns from metadata
    for col in meta.get("columns", []):
        name = col.get("name") or col.get("title", "?")
        glossary[name] = {
            "column": name,
            "origin": "original",
            "how": f"{col.get('data_type', '?')} field from source data",
            "intuition": col.get("title", name),
            "selection_outcome": None,
            "selection_reason": None,
        }

    # 2. Annotate with clean step descriptions (columns_affected per step)
    clean_state_path = ARTIFACTS_DIR / dataset_id / CLEAN_DIR / "state.json"
    if clean_state_path.exists():
        clean_state = json.loads(clean_state_path.read_text())
        for step in clean_state.get("step_log", []):
            desc = step.get("description", "")
            for col in step.get("columns_affected", []):
                if col in glossary:
                    glossary[col]["how"] = f"Cleaned: {desc}"
                else:
                    glossary[col] = {
                        "column": col,
                        "origin": "clean",
                        "how": desc,
                        "intuition": "",
                        "selection_outcome": None,
                        "selection_reason": None,
                    }

    # 3. Parse engineer pipeline.py for each step's docstring + new columns
    pipeline_path = ARTIFACTS_DIR / dataset_id / ENGINEER_DIR / "pipeline.py"
    if pipeline_path.exists():
        try:
            src = pipeline_path.read_text()
            tree = _ast.parse(src)
            for node in _ast.walk(tree):
                if isinstance(node, _ast.FunctionDef) and node.name.startswith("step_"):
                    docstring = _ast.get_docstring(node) or ""
                    # Heuristic: find df[...] = ... assignments to detect new columns
                    for child in _ast.walk(node):
                        if (isinstance(child, _ast.Assign)
                                and isinstance(child.targets[0], _ast.Subscript)
                                and isinstance(child.targets[0].value, _ast.Name)
                                and child.targets[0].value.id == "df"):
                            slice_node = child.targets[0].slice
                            col_name = (slice_node.s if isinstance(slice_node, _ast.Constant)
                                        and isinstance(slice_node.s, str) else None)
                            if col_name and col_name not in glossary:
                                step_label = node.name.replace("step_", "").replace("_", " ").strip("0123456789 ")
                                glossary[col_name] = {
                                    "column": col_name,
                                    "origin": "engineered",
                                    "how": f"{step_label}: {docstring[:120]}".strip(": "),
                                    "intuition": docstring[:200] if docstring else "",
                                    "selection_outcome": None,
                                    "selection_reason": None,
                                }
        except Exception:
            pass

    # 4. Annotate selection outcomes from feature_report
    feature_report = load_feature_report(dataset_id)
    if feature_report:
        llm = feature_report.get("llm_review", {})
        final_keep = set(llm.get("final_keep", []))
        track_b = set(feature_report.get("track_b", []))

        for col in final_keep:
            if col in glossary:
                track = "Track B (structural)" if col in track_b else "Track A (predictive)"
                glossary[col]["selection_outcome"] = f"kept — {track}"

        for override in llm.get("overrides", []):
            col = override.get("column")
            if col and col in glossary:
                action = override.get("action", "override")
                reason = override.get("reason", "")
                if action == "restore":
                    glossary[col]["selection_outcome"] = "kept — LLM override (restore)"
                    glossary[col]["selection_reason"] = reason
                elif action == "drop":
                    glossary[col]["selection_outcome"] = "dropped — LLM override"
                    glossary[col]["selection_reason"] = reason

        for dropped in feature_report.get("selection_report", {}).get("dropped", []):
            col = dropped.get("column")
            if col and col in glossary:
                if not glossary[col]["selection_outcome"]:
                    stage_name = f"S{dropped.get('stage', '?')} {dropped.get('stage_name', '')}"
                    glossary[col]["selection_outcome"] = f"dropped — {stage_name.strip()}"
                    glossary[col]["selection_reason"] = dropped.get("reason", "")

        # Mark remaining kept columns
        for col, entry in glossary.items():
            if entry["selection_outcome"] is None and col in final_keep:
                entry["selection_outcome"] = "kept"

    return list(glossary.values())


def load_endgame_charts(dataset_id: str) -> list[dict]:
    """Find endgame chart manifests in engineer runs."""
    lv2_dir = ARTIFACTS_DIR / dataset_id / ENGINEER_DIR
    charts = []
    if not lv2_dir.exists():
        return charts
    for run_dir in sorted(lv2_dir.iterdir()):
        manifest = run_dir / "manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text())
            for c in data.get("charts", []):
                c["run_dir"] = run_dir.name
                charts.append(c)
    return charts


def build_pipeline_summary(dataset_id: str) -> str:
    """Build a bounded pipeline summary from state.json step_log."""
    state = load_state_json(dataset_id)
    if not state:
        return "(no pipeline state found)"

    lines = [f"Pipeline: {state.get('steps_applied', '?')} steps, "
             f"{state['row_count']} rows, {len(state.get('current_columns', []))} cols"]

    step_log = state.get("step_log", [])
    for entry in step_log[:MAX_STEP_LOG_ENTRIES]:
        name = entry.get("step_name", "?")
        desc = entry.get("description", "")[:100]
        result = entry.get("result", "")[:60]
        cols_added = entry.get("columns_added", [])
        lines.append(f"  - {name}: {desc}")
        if cols_added:
            lines.append(f"    +cols: {', '.join(cols_added)}")

    if len(step_log) > MAX_STEP_LOG_ENTRIES:
        lines.append(f"  ... ({len(step_log) - MAX_STEP_LOG_ENTRIES} more steps)")

    # Sample records (bounded)
    samples = state.get("sample_records", [])[:MAX_SAMPLE_RECORDS]
    if samples:
        # Only show a subset of columns to avoid explosion
        all_cols = list(samples[0].keys()) if samples else []
        show_cols = all_cols[:10]  # max 10 columns in sample
        lines.append(f"\nSample records ({len(samples)} rows, showing {len(show_cols)}/{len(all_cols)} cols):")
        for rec in samples:
            trimmed = {k: rec[k] for k in show_cols if k in rec}
            lines.append(f"  {json.dumps(trimmed, default=str)[:200]}")

    return "\n".join(lines)


def build_feature_selection_summary(dataset_id: str) -> str:
    """Bounded summary of feature selection results."""
    report = load_feature_report(dataset_id)
    if not report:
        return "(no feature selection found)"

    lines = []
    sr = report.get("selection_report", {})
    llm = report.get("llm_review", {})

    # Stage summaries
    for stage in sr.get("stages", []):
        name = stage.get("name", "?")
        dropped = stage.get("dropped", 0)
        survivors = stage.get("survivors", "?")
        lines.append(f"S{stage['stage']} {name}: {survivors} survivors (dropped {dropped})")

    # Dropped columns
    dropped = sr.get("dropped", [])
    if dropped:
        lines.append(f"\nDropped ({len(dropped)}):")
        for d in dropped:
            lines.append(f"  - {d['column']}: {d['reason'][:80]}")

    # LLM overrides
    overrides = llm.get("overrides", [])
    if overrides:
        lines.append(f"\nLLM overrides ({len(overrides)}):")
        for o in overrides:
            lines.append(f"  - {o['action']} {o['column']}: {o['reason'][:80]}")

    # Final keep
    final = llm.get("final_keep", [])
    if final:
        lines.append(f"\nFinal columns ({len(final)}): {', '.join(final)}")

    # Leakage flags
    leakage = llm.get("leakage_flags", [])
    if leakage:
        lines.append(f"\nLeakage warnings: {', '.join(leakage)}")

    return "\n".join(lines)


def build_chart_descriptions(dataset_id: str, run_id: str) -> str:
    """List all endgame + selection charts with relative paths from the report run dir."""
    # Paths relative from {PHASE_DIR}/run-{id}/ to sibling phase dirs
    lines = []

    # Endgame charts (in engineer phase)
    charts = load_endgame_charts(dataset_id)
    if charts:
        lines.append(f"### Endgame charts ({ENGINEER_DIR})")
        for c in charts:
            rd = c.get("run_dir", "")
            path = f"../../{ENGINEER_DIR}/{rd}/charts/{c['filename']}"
            lines.append(f"- Image: `![{c['description']}]({path})`")
            lines.append(f"  Description: {c['description']}")

    # Selection charts
    select_dir = ARTIFACTS_DIR / dataset_id / SELECT_DIR
    if select_dir.exists():
        sel_runs = sorted([d for d in select_dir.iterdir() if d.is_dir() and d.name.startswith("run-")])
        if sel_runs:
            latest = sel_runs[-1]
            chart_dir = latest / "charts"
            if chart_dir.exists():
                sel_charts = sorted(chart_dir.iterdir())
                if sel_charts:
                    lines.append(f"\n### Feature selection charts ({SELECT_DIR})")
                    for p in sel_charts:
                        if p.suffix == ".png":
                            path = f"../../{SELECT_DIR}/{latest.name}/charts/{p.name}"
                            desc = p.stem.replace("_", " ")
                            lines.append(f"- Image: `![{desc}]({path})`")

    return "\n".join(lines) if lines else "(no charts found)"


def build_dataset_overview(meta: dict, state: dict | None) -> str:
    """Bounded dataset overview."""
    lines = [
        f"Title: {meta['name']}",
        f"Publisher: {meta.get('managed_by', '?')}",
        f"Format: {meta.get('format', '?')}",
        f"Coverage: {meta.get('coverage_start', '?')[:10]} → {meta.get('coverage_end', '?')[:10]}",
    ]
    if meta.get("description"):
        lines.append(f"Description: {meta['description'][:300]}")

    # Schema
    lines.append(f"\nSchema ({len(meta.get('columns', []))} columns):")
    for col in meta.get("columns", [])[:20]:
        lines.append(f"  - {col['title']} ({col['data_type']})")

    if state:
        lines.append(f"\nRows: {state.get('row_count', '?')}")
        lines.append(f"Engineered columns: {len(state.get('added_columns', []))}")

    return "\n".join(lines)


def load_and_replay(dataset_id: str) -> pd.DataFrame | None:
    """Load full CSV and replay clean → engineer pipelines, attach cluster labels.

    Returns engineered df or None.
    """
    csv_path = DATA_DIR / f"{dataset_id}.csv"
    if not csv_path.exists():
        print(f"  No CSV found at {csv_path}")
        return None

    raw_df = pd.read_csv(csv_path)
    df = raw_df.copy()
    print(f"  Loaded {len(df)} rows from CSV")

    # 1. Replay clean pipeline
    clean_pipeline_path = ARTIFACTS_DIR / dataset_id / CLEAN_DIR / "clean_pipeline.py"
    if clean_pipeline_path.exists():
        spec = importlib.util.spec_from_file_location("clean_pipeline", clean_pipeline_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        df = mod.run_pipeline(df)
        print(f"  Replayed clean pipeline: {len(df)} rows, {len(df.columns)} cols")

    # 2. Replay engineer pipeline
    pipeline_path = ARTIFACTS_DIR / dataset_id / ENGINEER_DIR / "pipeline.py"
    if pipeline_path.exists():
        spec = importlib.util.spec_from_file_location("pipeline", pipeline_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        df = mod.run_pipeline(df)
        print(f"  Replayed engineer pipeline: {len(df)} rows, {len(df.columns)} cols")

    # 3. Attach cluster labels (index-join, tolerates row-count mismatches)
    cluster_labels_path = ARTIFACTS_DIR / dataset_id / CLUSTER_DIR / "cluster_labels.csv"
    if cluster_labels_path.exists():
        labels_df = pd.read_csv(cluster_labels_path, index_col=0)
        label_cols = [c for c in labels_df.columns if c in ("cluster_label", "cluster_name")]
        if label_cols:
            df = df.join(labels_df[label_cols], how="left")
            print(f"  Attached cluster labels: {', '.join(label_cols)}")

    return df


def run_modeling(df: pd.DataFrame, feature_report: dict,
                 chart_dir: Path) -> dict:
    """Fit models and generate Tier 2 charts. Returns summary for LLM prompt.

    Generic: picks OLS or tree based on task_type from feature_report.
    """
    from lib.eda.modeling import (
        fit_ols, coefficient_plot, partial_residual_plot, interaction_plot,
        fit_tree, tree_feature_importance_plot, shap_dependence_plot,
        confusion_matrix_plot, roc_auc_plot,
    )
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chart_dir.mkdir(parents=True, exist_ok=True)

    target_col = feature_report.get("target_col")
    task_type = feature_report.get("task_type", "regress")
    final_keep = feature_report.get("llm_review", {}).get("final_keep", [])

    if not target_col or not final_keep:
        return {"error": "missing target or features in feature_report"}

    # Filter to columns that exist in df and separate target from features
    features = [c for c in final_keep if c != target_col and c in df.columns]
    if target_col not in df.columns:
        return {"error": f"target {target_col} not in dataframe"}

    # Exclude datetime columns — models can't handle them directly
    features = [c for c in features
                if not pd.api.types.is_datetime64_any_dtype(df[c])]

    # Split numeric vs categorical features for OLS
    numeric_features = [c for c in features if pd.api.types.is_numeric_dtype(df[c])]
    cat_features = [c for c in features
                    if not pd.api.types.is_numeric_dtype(df[c])
                    and df[c].dtype in ("object", "category")]

    summary = {
        "task_type": task_type,
        "target": target_col,
        "n_features": len(features),
        "n_rows": len(df),
        "charts": [],
    }

    def _save(fig, name, desc):
        path = chart_dir / name
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        summary["charts"].append({"filename": name, "description": desc})
        print(f"    Chart: {name}")

    # --- Regression path ---
    if task_type == "regress":
        # OLS on log(target) with numeric features
        if numeric_features:
            print("  Fitting OLS...")
            try:
                ols = fit_ols(df, target_col, numeric_features, log_target=True)
                summary["ols"] = {
                    "r_squared": round(ols.r_squared, 4),
                    "adj_r_squared": round(ols.adj_r_squared, 4),
                    "n_obs": ols.n_obs,
                    "top_coefficients": ols.coefficients[
                        ols.coefficients["feature"] != "const"
                    ].nlargest(5, "coef")[["feature", "coef", "p_value"]].to_dict("records"),
                }

                # Coefficient plot
                fig, desc = coefficient_plot(ols)
                _save(fig, "ols_coefficients.png", desc)

                # Partial residual for top 2 features by |coef|
                coef_df = ols.coefficients[ols.coefficients["feature"] != "const"].copy()
                coef_df["abs_coef"] = coef_df["coef"].abs()
                top_feats = coef_df.nlargest(2, "abs_coef")["feature"].tolist()
                for feat in top_feats:
                    if feat in df.columns:
                        try:
                            fig, desc = partial_residual_plot(df, ols, feat)
                            _save(fig, f"partial_resid_{feat}.png", desc)
                        except Exception as e:
                            print(f"    Skipped partial residual for {feat}: {e}")

                # Interaction plot: top numeric feature × top categorical
                # Use the full df — interaction_plot only needs target + the two features
                if numeric_features and cat_features:
                    top_num = top_feats[0] if top_feats else numeric_features[0]
                    top_cat = cat_features[0]
                    try:
                        # Build a minimal summary with all features for interaction
                        from lib.eda.modeling import ModelSummary
                        interaction_summary = ModelSummary(
                            target=target_col, features=numeric_features + cat_features,
                            log_target=True, r_squared=ols.r_squared,
                            adj_r_squared=ols.adj_r_squared, n_obs=ols.n_obs,
                            coefficients=ols.coefficients, residuals=ols.residuals,
                            fitted_values=ols.fitted_values, aic=ols.aic, bic=ols.bic,
                        )
                        fig, desc = interaction_plot(df, interaction_summary, top_num, top_cat)
                        _save(fig, f"interaction_{top_num}_by_{top_cat}.png", desc)
                    except Exception as e:
                        print(f"    Skipped interaction plot: {e}")

            except Exception as e:
                print(f"  OLS failed: {e}")
                summary["ols_error"] = str(e)

        # Tree model for SHAP dependence (complementary to OLS)
        print("  Fitting LightGBM (regress)...")
        try:
            tree = fit_tree(df, target_col, features, task="regress", log_target=True)
            summary["tree"] = {
                "r2": round(tree.metric_value, 4),
                "n_train": tree.n_train,
                "n_test": tree.n_test,
            }

            fig, desc = tree_feature_importance_plot(tree)
            _save(fig, "tree_importance.png", desc)

            # SHAP dependence for top feature
            top_feat = tree.feature_importance.iloc[0]["feature"]
            if top_feat in df.columns:
                fig, desc = shap_dependence_plot(tree, top_feat)
                _save(fig, f"shap_dep_{top_feat}.png", desc)

        except Exception as e:
            print(f"  Tree model failed: {e}")
            summary["tree_error"] = str(e)

    # --- Classification path ---
    elif task_type == "classify":
        print("  Fitting LightGBM (classify)...")
        try:
            tree = fit_tree(df, target_col, features, task="classify")
            summary["tree"] = {
                "f1": round(tree.metric_value, 4),
                "n_train": tree.n_train,
                "n_test": tree.n_test,
                "n_classes": int(tree.y_test.nunique()),
            }

            fig, desc = tree_feature_importance_plot(tree)
            _save(fig, "tree_importance.png", desc)

            fig, desc = confusion_matrix_plot(tree)
            _save(fig, "confusion_matrix.png", desc)

            if tree.y_prob is not None:
                try:
                    fig, desc = roc_auc_plot(tree)
                    _save(fig, "roc_auc.png", desc)
                except Exception as e:
                    print(f"    ROC-AUC skipped: {e}")

            # SHAP dependence for top feature
            top_feat = tree.feature_importance.iloc[0]["feature"]
            if top_feat in df.columns:
                fig, desc = shap_dependence_plot(tree, top_feat)
                _save(fig, f"shap_dep_{top_feat}.png", desc)

        except Exception as e:
            print(f"  Tree model failed: {e}")
            summary["tree_error"] = str(e)

    return summary


def build_modeling_summary(model_result: dict, run_id: str) -> str:
    """Format modeling results for the LLM prompt."""
    if not model_result or "error" in model_result:
        return f"(modeling skipped: {model_result.get('error', 'unknown')})"

    lines = [f"Task: {model_result['task_type']}, target: {model_result['target']}, "
             f"{model_result['n_features']} features, {model_result['n_rows']:,} rows"]

    if "ols" in model_result:
        ols = model_result["ols"]
        lines.append(f"\nOLS on log({model_result['target']}): R²={ols['r_squared']}, "
                     f"adj_R²={ols['adj_r_squared']}, n={ols['n_obs']:,}")
        lines.append("Top coefficients (on log scale):")
        for c in ols.get("top_coefficients", []):
            sig = "***" if c["p_value"] < 0.001 else "**" if c["p_value"] < 0.01 else "*" if c["p_value"] < 0.05 else ""
            lines.append(f"  {c['feature']}: {c['coef']:.4f} {sig}")

    if "tree" in model_result:
        tree = model_result["tree"]
        if model_result["task_type"] == "regress":
            lines.append(f"\nLightGBM: R²={tree['r2']}, train={tree['n_train']:,}, test={tree['n_test']:,}")
        else:
            lines.append(f"\nLightGBM: F1={tree['f1']}, {tree['n_classes']} classes, "
                         f"train={tree['n_train']:,}, test={tree['n_test']:,}")

    if model_result.get("charts"):
        lines.append(f"\n### Model charts ({PHASE_DIR})")
        for c in model_result["charts"]:
            path = f"charts/{c['filename']}"
            lines.append(f"- Image: `![{c['description']}]({path})`")

    return "\n".join(lines)


def _fix_chart_paths(report_text: str, dataset_id: str, report_run_dir: Path) -> str:
    """Rewrite broken chart image paths in LLM-generated report.

    The LLM often writes bare `charts/filename.png` for charts that actually
    live in sibling phase directories. This function:
    1. Builds a filename→absolute-path map from all chart dirs in the dataset.
    2. Scans the report for ![...](path) references.
    3. For each reference, if the path doesn't resolve from report_run_dir,
       look up the filename in the map and replace with the correct relative path.
    """
    dataset_root = ARTIFACTS_DIR / dataset_id

    # Build filename → absolute path index.
    # Sort by path so that the current report_run_dir's charts overwrite earlier runs.
    # This ensures model charts reference the current run, not a stale previous one.
    chart_index: dict[str, Path] = {}
    all_charts = sorted(dataset_root.rglob("charts/*.png"), key=lambda p: (
        0 if p.is_relative_to(report_run_dir) else 1,  # current run first
        str(p)
    ))
    for png in all_charts:
        chart_index[png.name] = png

    def resolve_img(m: re.Match) -> str:
        alt = m.group(1)
        path_str = m.group(2)

        # Try to resolve as-is relative to report_run_dir
        candidate = (report_run_dir / path_str).resolve()
        if candidate.exists():
            return m.group(0)  # already correct

        # Try to resolve by filename only
        filename = Path(path_str).name
        if filename in chart_index:
            abs_chart = chart_index[filename]
            rel = Path(os.path.relpath(abs_chart, report_run_dir))
            return f"![{alt}]({rel.as_posix()})"

        # Can't resolve — leave as-is (broken path is visible in the rendered report)
        return m.group(0)

    return re.sub(r'!\[([^\]]*)\]\(([^)]+\.png)\)', resolve_img, report_text)


def generate_report(dataset_id: str) -> str:
    """Generate the full research report."""
    steps = []
    ctx = RunContext(dataset_id, ACTION, ACTION_CODE, "reporter")
    run_id = ctx.run_id

    # 2. Gather all context (bounded)
    meta = fetch_metadata(dataset_id)
    state = load_state_json(dataset_id)
    human_notes = load_human_notes(dataset_id)
    findings = load_prior_artifacts(dataset_id, before_action_code=ACTION_CODE)

    dataset_overview = build_dataset_overview(meta, state)
    pipeline_summary = build_pipeline_summary(dataset_id)
    feature_selection = build_feature_selection_summary(dataset_id)
    chart_descriptions = build_chart_descriptions(dataset_id, run_id)

    # Truncate findings to prevent context explosion
    if findings and len(findings) > MAX_FINDINGS_CHARS:
        findings = findings[:MAX_FINDINGS_CHARS] + "\n... (truncated, see individual artifacts)"

    steps.append({"name": "gather_context",
                   "detail": f"overview={len(dataset_overview)}c, pipeline={len(pipeline_summary)}c, "
                             f"selection={len(feature_selection)}c, charts={len(chart_descriptions)}c"})

    # 3. Determine target + run modeling
    feature_report = load_feature_report(dataset_id)
    target_col = feature_report.get("target_col", "unknown") if feature_report else "unknown"

    # 3b. Load data, replay pipeline, fit models, generate charts
    model_summary = "(no modeling — missing data or feature report)"
    model_result = {}
    run_dir = get_run_dir(dataset_id, run_id)
    if feature_report:
        print("Loading data and replaying pipeline...")
        df = load_and_replay(dataset_id)
        if df is not None:
            print("Running modeling...")
            model_result = run_modeling(df, feature_report, run_dir / "charts")
            model_summary = build_modeling_summary(model_result, run_id)
            print(f"  Modeling: {len(model_result.get('charts', []))} charts generated")
            del df  # free memory

    steps.append({"name": "modeling", "detail": model_summary[:200]})

    # 4. Build prompt
    print("Building report prompt...")
    prompt_template = load_prompt(PROMPT_NAME)
    prompt = Template(prompt_template).safe_substitute(
        title=meta["name"],
        target_col=target_col,
        dataset_overview=dataset_overview,
        findings_summary=findings or "_(no prior findings)_",
        feature_selection=feature_selection,
        chart_descriptions=chart_descriptions,
        pipeline_summary=pipeline_summary,
        human_notes=human_notes or "_(none)_",
        modeling_results=model_summary,
    )

    # Guard: check prompt size
    print(f"  Prompt size: {len(prompt)} chars")
    if len(prompt) > 30000:
        print(f"  WARNING: prompt is large ({len(prompt)} chars). Trimming context.")
        # Trim the longest section
        prompt = prompt[:30000] + "\n\n(context truncated for token budget)"
    steps.append({"name": "build_prompt", "detail": f"{len(prompt)} chars"})

    # 5. Call LLM for report generation
    print("Generating report...")
    report_text = call_llm(prompt, max_tokens=4096)
    print(f"  Report: {len(report_text)} chars, {report_text.count(chr(10))} lines")
    steps.append({"name": "generate_report", "detail": f"{len(report_text)} chars"})

    # 6. Fix chart paths — LLM frequently writes bare `charts/filename.png` for charts
    # that live in sibling phase directories (30-select, 20-engineer, etc.).
    # Build a filename→correct-relative-path map from all known chart locations,
    # then rewrite any unresolvable references in the report.
    report_text = _fix_chart_paths(report_text, dataset_id, run_dir)

    # 7. Save report and glossary
    report_path = run_dir / "report.md"
    report_path.write_text(report_text)
    print(f"  Saved: {report_path}")

    # Build and save column glossary
    glossary = build_column_glossary(dataset_id, meta)
    glossary_path = ARTIFACTS_DIR / dataset_id / PHASE_DIR / "glossary.json"
    glossary_path.parent.mkdir(parents=True, exist_ok=True)
    glossary_path.write_text(json.dumps(glossary, indent=2))
    print(f"  Glossary: {glossary_path} ({len(glossary)} columns)")

    # Save run metadata
    run_meta = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "target_col": target_col,
        "task_type": feature_report.get("task_type") if feature_report else None,
        "row_count": state.get("row_count") if state else None,
        "pipeline_steps": state.get("steps_applied") if state else None,
        "features_selected": len(feature_report.get("llm_review", {}).get("final_keep", [])) if feature_report else None,
        "modeling": {k: v for k, v in model_result.items() if k != "charts"},
        "model_charts": len(model_result.get("charts", [])),
        "llm_model": DEFAULT_MODEL,
        "prompt_chars": len(prompt),
        "report_chars": len(report_text),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = run_dir / "run_metadata.json"
    meta_path.write_text(json.dumps(run_meta, indent=2))

    print(f"\n=== Report Complete ===")
    print(f"  Report: {report_path}")
    print(f"  Metadata: {meta_path}")

    # Set flags
    if "ols" in model_result:
        set_flag(dataset_id, "ols_fitted", run_id=run_id,
                 detail=f"R²={model_result['ols'].get('r_squared', '?')}")
    if "tree" in model_result:
        set_flag(dataset_id, "tree_fitted", run_id=run_id)
    set_flag(dataset_id, "report_generated", run_id=run_id,
             detail=f"{len(report_text)} chars, {len(model_result.get('charts', []))} model charts")

    # Append to session notebook
    try:
        nb = nb_lib.load_or_create(dataset_id)
        ols = model_result.get("ols", {})
        feature_report = load_feature_report(dataset_id)
        target_col = feature_report.get("target_col", "?") if feature_report else "?"
        selected = feature_report.get("llm_review", {}).get("final_keep", []) if feature_report else []
        nb_lib.add_phase_section(
            nb,
            action_code=ACTION_CODE,
            action=ACTION,
            verdict="complete",
            llm_narrative=report_text[:1500] + ("\n\n*(truncated — see report.md for full text)*"
                                                  if len(report_text) > 1500 else ""),
            code_cells=[
                # Reproduce the OLS model
                f"# Ridge model (log-transformed target)\n"
                f"from sklearn.linear_model import Ridge\n"
                f"from sklearn.model_selection import train_test_split\n"
                f"import numpy as np, pandas as pd\n\n"
                f"_target = {target_col!r}\n"
                f"_features = {selected!r}\n"
                f"_features = [f for f in _features if f in df.columns]\n"
                f"_X = df[_features].select_dtypes(include='number').fillna(0)\n"
                f"_y = np.log1p(df[_target])\n"
                f"_X_train, _X_test, _y_train, _y_test = train_test_split(_X, _y, test_size=0.2, random_state=42)\n"
                f"_model = Ridge().fit(_X_train, _y_train)\n"
                f"print(f'R² test: {{_model.score(_X_test, _y_test):.4f}}')\n"
                f"pd.Series(_model.coef_, index=_X.columns).sort_values().plot.barh(figsize=(8,6), title='Ridge coefficients')",

                # Actual vs predicted scatter
                f"# Actual vs predicted\n"
                f"import matplotlib.pyplot as plt, numpy as np\n"
                f"_n_sample = min(2000, len(_X_test))\n"
                f"_idx = np.random.choice(len(_X_test), _n_sample, replace=False)\n"
                f"_actual = np.expm1(_y_test.iloc[_idx])\n"
                f"_pred   = np.expm1(_model.predict(_X_test.iloc[_idx]))\n"
                f"fig, ax = plt.subplots(figsize=(6, 6))\n"
                f"ax.scatter(_actual, _pred, alpha=0.3, s=6, color='steelblue')\n"
                f"_lo, _hi = _actual.min(), _actual.max()\n"
                f"ax.plot([_lo, _hi], [_lo, _hi], 'r--', linewidth=1)\n"
                f"ax.set_xlabel('Actual'); ax.set_ylabel('Predicted')\n"
                f"ax.set_title(f'Actual vs Predicted (Ridge, n={{_n_sample}})')\n"
                f"plt.tight_layout(); plt.show()",

                # Target distribution by cluster (if cluster label exists)
                f"# Target distribution by cluster\n"
                f"import matplotlib.pyplot as plt\n"
                f"if 'cluster_label' in df.columns:\n"
                f"    fig, ax = plt.subplots(figsize=(8, 5))\n"
                f"    for lbl, grp in df.groupby('cluster_label'):\n"
                f"        grp[_target].hist(bins=50, ax=ax, alpha=0.55, density=True, label=str(lbl))\n"
                f"    ax.set_xlabel(_target); ax.set_title(f'{{_target}} distribution by cluster')\n"
                f"    ax.legend(); plt.tight_layout(); plt.show()\n"
                f"else:\n"
                f"    df[_target].hist(bins=60, figsize=(8, 4), color='steelblue', alpha=0.8, edgecolor='none')\n"
                f"    plt.title(f'{{_target}} distribution'); plt.tight_layout(); plt.show()",
            ],
        )
        nb_lib.save(nb, dataset_id)
        print(f"  Notebook updated: session.ipynb")
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"  Notebook write failed: {e}")

    # Record run in DB
    ctx.finish(
        verdict="complete",
        verdict_reason=f"{len(report_text)} chars, {len(model_result.get('charts', []))} model charts",
        artifact_paths=[
            f"artifacts/{dataset_id}/{PHASE_DIR}/run-{run_id}/report.md",
            f"artifacts/{dataset_id}/{PHASE_DIR}/glossary.json",
        ],
        prompt_template=PROMPT_NAME,
    )
    ctx.conn.execute(
        "UPDATE datasets SET max_action_code = '50', updated_at = datetime('now') WHERE id = ?",
        (dataset_id,),
    )
    ctx.conn.commit()
    ctx.close()

    return report_text


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m agents.reporter <dataset_id>")
        sys.exit(1)

    dataset_id = sys.argv[1]
    generate_report(dataset_id)


if __name__ == "__main__":
    main()
