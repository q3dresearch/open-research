"""Staged feature selection — cheap to expensive, unsupervised to supervised.

Stage 1: Cheap pruning (no model, no target)
Stage 2: Correlation clustering (keep one representative per cluster)
Stage 3: Pseudo-target discovery (which columns are redundant vs novel)
Stage 4: Lightweight supervised scoring (MI, F-score — if target available)
Stage 5: Expensive attribution (SHAP, permutation — top survivors only)
Stage 6: Chart filter (keep time/category even if low predictive signal)

Design rule: never let expensive methods decide the first cut.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field


@dataclass
class SelectionReport:
    """Accumulates decisions across all stages."""
    dropped: list[dict] = field(default_factory=list)  # {column, stage, reason}
    kept: list[str] = field(default_factory=list)
    chart_retained: list[dict] = field(default_factory=list)  # {column, reason}
    stage_summaries: list[dict] = field(default_factory=list)
    scores: dict = field(default_factory=dict)  # column -> {metric: value}
    # Intermediate data for charting (populated by stages)
    intermediates: dict = field(default_factory=dict)

    def drop(self, col: str, stage: int, reason: str):
        self.dropped.append({"column": col, "stage": stage, "reason": reason})

    def summary(self) -> dict:
        return {
            "kept": self.kept,
            "dropped": self.dropped,
            "chart_retained": self.chart_retained,
            "stages": self.stage_summaries,
            "scores": self.scores,
        }


# ---------------------------------------------------------------------------
# Stage 1: Cheap pruning (unsupervised, no model)
# ---------------------------------------------------------------------------

def stage1_cheap_prune(df: pd.DataFrame, report: SelectionReport,
                       target_col: str | None = None,
                       missing_threshold: float = 0.7,
                       variance_threshold: float = 0.001,
                       unique_ratio_threshold: float = 0.95) -> list[str]:
    """Drop obvious garbage: high-missing, near-constant, ID-like columns.

    Returns list of surviving column names.
    """
    survivors = []
    dropped_count = 0

    for col in df.columns:
        # Never prune the target
        if col == target_col:
            survivors.append(col)
            continue

        # Missingness
        miss_pct = df[col].isna().mean()
        if miss_pct > missing_threshold:
            report.drop(col, 1, f"missing {miss_pct:.0%}")
            dropped_count += 1
            continue

        # Near-zero variance (numeric only)
        if pd.api.types.is_numeric_dtype(df[col]):
            non_null = df[col].dropna()
            if len(non_null) > 0 and non_null.std() < variance_threshold:
                report.drop(col, 1, f"near-zero variance (std={non_null.std():.6f})")
                dropped_count += 1
                continue

        # ID columns — only check non-numeric (string columns with near-unique values)
        # Numeric columns with high uniqueness are continuous features, not IDs
        nunique = df[col].nunique()
        if not pd.api.types.is_numeric_dtype(df[col]):
            if nunique / max(len(df), 1) > unique_ratio_threshold:
                report.drop(col, 1, f"ID-like column (unique ratio={nunique/len(df):.2f})")
                dropped_count += 1
                continue

        # Constant columns
        if nunique <= 1:
            report.drop(col, 1, "constant (1 unique value)")
            dropped_count += 1
            continue

        survivors.append(col)

    report.stage_summaries.append({
        "stage": 1, "name": "cheap_prune",
        "input_cols": len(df.columns), "dropped": dropped_count,
        "survivors": len(survivors),
    })
    return survivors


# ---------------------------------------------------------------------------
# Stage 2: Correlation clustering (keep one representative per cluster)
# ---------------------------------------------------------------------------

def stage2_correlation_cluster(df: pd.DataFrame, survivors: list[str],
                               report: SelectionReport,
                               corr_threshold: float = 0.85) -> list[str]:
    """Cluster correlated numeric features, keep the best representative.

    Representative selection: highest variance, then lowest missingness,
    then most interpretable (shortest name as proxy).
    """
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform

    numeric_survivors = [c for c in survivors if pd.api.types.is_numeric_dtype(df[c])]
    non_numeric = [c for c in survivors if c not in numeric_survivors]

    if len(numeric_survivors) <= 1:
        report.stage_summaries.append({
            "stage": 2, "name": "correlation_cluster",
            "input_cols": len(survivors), "dropped": 0,
            "survivors": len(survivors), "clusters": 0,
        })
        return survivors

    # Correlation matrix → distance matrix
    corr = df[numeric_survivors].corr().abs()
    # Ensure no NaN (replace with 0 correlation = max distance)
    corr = corr.fillna(0)
    dist_arr = (1 - corr).to_numpy().copy()
    np.fill_diagonal(dist_arr, 0)

    # Hierarchical clustering
    condensed = squareform(dist_arr, checks=False)
    Z = linkage(condensed, method="average")
    labels = fcluster(Z, t=1 - corr_threshold, criterion="distance")

    # For each cluster, pick the best representative
    clusters = {}
    for col, label in zip(numeric_survivors, labels):
        clusters.setdefault(label, []).append(col)

    kept_numeric = []
    dropped_count = 0
    for label, cols in clusters.items():
        if len(cols) == 1:
            kept_numeric.append(cols[0])
            continue

        # Score each: higher variance = better, lower missingness = better
        scores = []
        for c in cols:
            var = df[c].var() if df[c].notna().sum() > 1 else 0
            miss = df[c].isna().mean()
            # Prefer: high variance, low missingness, short name (interpretable)
            scores.append((var, -miss, -len(c), c))

        scores.sort(reverse=True)
        representative = scores[0][3]
        kept_numeric.append(representative)

        for _, _, _, c in scores[1:]:
            report.drop(c, 2, f"correlated with {representative} (cluster {label})")
            dropped_count += 1

    new_survivors = non_numeric + kept_numeric

    # Store intermediates for charting
    report.intermediates["corr_matrix"] = corr
    report.intermediates["corr_columns"] = numeric_survivors
    report.intermediates["linkage"] = Z
    report.intermediates["cluster_labels"] = {col: int(lbl) for col, lbl in zip(numeric_survivors, labels)}
    report.intermediates["clusters"] = clusters

    report.stage_summaries.append({
        "stage": 2, "name": "correlation_cluster",
        "input_cols": len(survivors), "dropped": dropped_count,
        "survivors": len(new_survivors),
        "clusters": len(clusters),
    })
    return new_survivors


# ---------------------------------------------------------------------------
# Stage 3: Pseudo-target discovery (which columns are novel vs redundant)
# ---------------------------------------------------------------------------

def stage3_pseudo_target(df: pd.DataFrame, survivors: list[str],
                         report: SelectionReport,
                         target_col: str | None = None,
                         redundancy_threshold: float = 0.95) -> list[str]:
    """For each numeric column, predict it from the others using a simple model.

    Highly predictable columns are redundant (derived from others).
    Skips the target column (never drops it as redundant).
    Returns survivors with redundancy scores attached to report.
    """
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    numeric_survivors = [c for c in survivors
                         if pd.api.types.is_numeric_dtype(df[c]) and c != target_col]
    non_numeric = [c for c in survivors if c not in numeric_survivors]
    # Ensure target stays in non_numeric passthrough
    if target_col and target_col in survivors and target_col not in non_numeric:
        non_numeric.append(target_col)

    if len(numeric_survivors) <= 2:
        report.stage_summaries.append({
            "stage": 3, "name": "pseudo_target",
            "input_cols": len(survivors), "dropped": 0,
            "survivors": len(survivors),
        })
        return survivors

    # Prepare numeric matrix (fill NaN, scale)
    num_df = df[numeric_survivors].fillna(0)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(num_df)

    predictability = {}
    for i, col in enumerate(numeric_survivors):
        X = np.delete(scaled, i, axis=1)
        y = scaled[:, i]
        model = Ridge(alpha=1.0)
        model.fit(X, y)
        r2 = model.score(X, y)
        predictability[col] = round(r2, 4)

    # Store predictability for charting
    report.intermediates["predictability"] = predictability

    # Flag highly predictable as redundant
    dropped_count = 0
    kept_numeric = []
    for col in numeric_survivors:
        r2 = predictability[col]
        report.scores.setdefault(col, {})["predictability_r2"] = r2
        if r2 > redundancy_threshold:
            report.drop(col, 3, f"redundant (R²={r2:.3f} from other features)")
            dropped_count += 1
        else:
            kept_numeric.append(col)

    new_survivors = non_numeric + kept_numeric
    report.stage_summaries.append({
        "stage": 3, "name": "pseudo_target",
        "input_cols": len(survivors), "dropped": dropped_count,
        "survivors": len(new_survivors),
    })
    return new_survivors


# ---------------------------------------------------------------------------
# Stage 4: Lightweight supervised scoring (if target available)
# ---------------------------------------------------------------------------

def stage4_light_scoring(df: pd.DataFrame, survivors: list[str],
                         target_col: str, report: SelectionReport,
                         drop_bottom_n: int = 0) -> list[str]:
    """Score features by mutual information and correlation with target.

    Does NOT drop by default (drop_bottom_n=0) — just scores.
    The LLM decides what to drop using these scores.
    """
    from sklearn.feature_selection import mutual_info_regression, mutual_info_classif

    feature_cols = [c for c in survivors if c != target_col]
    numeric_features = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df[c])]

    if not numeric_features or target_col not in df.columns:
        report.stage_summaries.append({
            "stage": 4, "name": "light_scoring",
            "input_cols": len(survivors), "dropped": 0,
            "survivors": len(survivors), "note": "skipped (no target or no numeric features)",
        })
        return survivors

    X = df[numeric_features].fillna(0)
    y = df[target_col]

    # Choose MI variant based on target type
    is_classify = y.nunique() <= 20
    mi_func = mutual_info_classif if is_classify else mutual_info_regression
    mi_scores = mi_func(X, y, random_state=42)

    # Correlation with target
    corr_scores = X.corrwith(y).abs().fillna(0)

    for col, mi, corr in zip(numeric_features, mi_scores, corr_scores):
        report.scores.setdefault(col, {}).update({
            "mutual_info": round(float(mi), 4),
            "target_corr": round(float(corr), 4),
        })

    # Non-numeric features get scored differently
    for col in feature_cols:
        if col not in numeric_features:
            report.scores.setdefault(col, {})["mutual_info"] = None
            report.scores.setdefault(col, {})["target_corr"] = None

    # Optionally drop bottom N by MI
    dropped_count = 0
    new_survivors = list(survivors)
    if drop_bottom_n > 0:
        ranked = sorted(zip(numeric_features, mi_scores), key=lambda x: x[1])
        for col, mi in ranked[:drop_bottom_n]:
            report.drop(col, 4, f"lowest MI score ({mi:.4f})")
            new_survivors.remove(col)
            dropped_count += 1

    report.stage_summaries.append({
        "stage": 4, "name": "light_scoring",
        "input_cols": len(survivors), "dropped": dropped_count,
        "survivors": len(new_survivors),
        "task_type": "classify" if is_classify else "regress",
    })
    return new_survivors


# ---------------------------------------------------------------------------
# Stage 5: Expensive attribution (SHAP — only on survivors)
# ---------------------------------------------------------------------------

def stage5_shap_scores(df: pd.DataFrame, survivors: list[str],
                       target_col: str, report: SelectionReport) -> list[str]:
    """Run SHAP on surviving numeric features against the target.

    Does NOT drop columns — only scores. The LLM makes final decisions.
    Requires: lightgbm, shap
    """
    from lightgbm import LGBMClassifier, LGBMRegressor
    import shap

    feature_cols = [c for c in survivors if c != target_col and pd.api.types.is_numeric_dtype(df[c])]
    if len(feature_cols) < 2:
        report.stage_summaries.append({
            "stage": 5, "name": "shap_scores",
            "input_cols": len(survivors), "dropped": 0,
            "survivors": len(survivors), "note": "skipped (< 2 numeric features)",
        })
        return survivors

    X = df[feature_cols].fillna(0)
    y = df[target_col]

    is_classify = y.nunique() <= 20
    if is_classify:
        model = LGBMClassifier(colsample_bytree=0.8, verbose=-1, n_estimators=100)
    else:
        model = LGBMRegressor(colsample_bytree=0.8, verbose=-1, n_estimators=100)

    # Use a sample if dataset is large
    if len(X) > 5000:
        sample_idx = X.sample(5000, random_state=42).index
        model.fit(X.loc[sample_idx], y.loc[sample_idx])
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X.loc[sample_idx])
    else:
        model.fit(X, y)
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)

    # For multiclass, average across classes
    if isinstance(shap_values, list):
        shap_abs = np.mean([np.abs(sv) for sv in shap_values], axis=0)
    else:
        shap_abs = np.abs(shap_values)

    mean_shap = shap_abs.mean(axis=0)
    for col, sv in zip(feature_cols, mean_shap):
        report.scores.setdefault(col, {})["shap"] = round(float(sv), 6)

    report.stage_summaries.append({
        "stage": 5, "name": "shap_scores",
        "input_cols": len(survivors), "dropped": 0,
        "survivors": len(survivors),
        "features_scored": len(feature_cols),
    })
    return survivors


# ---------------------------------------------------------------------------
# Stage 6: Chart filter (domain-aware retention)
# ---------------------------------------------------------------------------

def stage6_chart_filter(df: pd.DataFrame, survivors: list[str],
                        report: SelectionReport) -> list[str]:
    """Identify columns that should be retained for charts even if low-signal.

    Detects: datetime columns, low-cardinality categoricals (good for segmentation),
    and geographic/location columns.
    """
    for col in survivors:
        dtype = df[col].dtype

        # Datetime columns → time series charts
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            report.chart_retained.append({"column": col, "reason": "datetime — time series charts"})
            continue

        # Low-cardinality categoricals → segmentation/faceting
        if dtype == "object" or dtype.name == "category":
            nunique = df[col].nunique()
            if 2 <= nunique <= 30:
                report.chart_retained.append({
                    "column": col,
                    "reason": f"categorical ({nunique} values) — segmentation/faceting",
                })

    report.stage_summaries.append({
        "stage": 6, "name": "chart_filter",
        "chart_retained": len(report.chart_retained),
    })
    return survivors


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_selection_pipeline(df: pd.DataFrame, target_col: str | None = None,
                           run_shap: bool = True) -> SelectionReport:
    """Run the complete staged feature selection pipeline.

    Args:
        df: DataFrame with all features (post-engineer pipeline)
        target_col: Column to predict (None = skip supervised stages)
        run_shap: Whether to run expensive SHAP scoring (Stage 5)

    Returns: SelectionReport with all decisions and scores
    """
    report = SelectionReport()
    cols = list(df.columns)

    # Stage 1: Cheap pruning
    survivors = stage1_cheap_prune(df, report, target_col=target_col)

    # Stage 2: Correlation clustering
    survivors = stage2_correlation_cluster(df, survivors, report)

    # Stage 3: Pseudo-target discovery
    survivors = stage3_pseudo_target(df, survivors, report, target_col=target_col)

    # Stage 4-5: Supervised (only if target provided)
    if target_col and target_col in survivors:
        survivors = stage4_light_scoring(df, survivors, target_col, report)
        if run_shap:
            survivors = stage5_shap_scores(df, survivors, target_col, report)

    # Stage 6: Chart filter (always runs)
    survivors = stage6_chart_filter(df, survivors, report)

    report.kept = survivors
    return report
