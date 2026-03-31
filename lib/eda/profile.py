"""Statistical profiling — shape, dtypes, nulls, outliers, duplicates."""

import pandas as pd
from pathlib import Path


def basic_profile(df: pd.DataFrame) -> dict:
    """Generate a statistical profile of a DataFrame."""
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    # IQR-based outlier detection
    outlier_pcts = {}
    if numeric_cols:
        q1 = df[numeric_cols].quantile(0.25)
        q3 = df[numeric_cols].quantile(0.75)
        iqr = q3 - q1
        outliers = (df[numeric_cols] < (q1 - 1.5 * iqr)) | (df[numeric_cols] > (q3 + 1.5 * iqr))
        outlier_pcts = (outliers.sum() / len(df) * 100).round(1).to_dict()

    profile = {
        "row_count": len(df),
        "col_count": len(df.columns),
        "numeric_cols": numeric_cols,
        "categorical_cols": cat_cols,
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_total": int(df.isna().sum().sum()),
        "columns": [],
    }

    for col in df.columns:
        info = {
            "name": col,
            "dtype": str(df[col].dtype),
            "null_count": int(df[col].isna().sum()),
            "null_pct": round(df[col].isna().mean() * 100, 1),
            "unique_count": int(df[col].nunique()),
        }
        if pd.api.types.is_numeric_dtype(df[col]):
            desc = df[col].describe()
            if "min" in desc.index:
                info["min"] = float(desc["min"]) if pd.notna(desc["min"]) else None
                info["max"] = float(desc["max"]) if pd.notna(desc["max"]) else None
                info["mean"] = round(float(desc["mean"]), 4) if pd.notna(desc["mean"]) else None
                info["std"] = round(float(desc["std"]), 4) if pd.notna(desc["std"]) else None
                info["median"] = float(desc["50%"]) if pd.notna(desc["50%"]) else None
            info["outlier_pct"] = outlier_pcts.get(col, 0.0)
        else:
            top = df[col].value_counts().head(5)
            info["top_values"] = {str(k): int(v) for k, v in top.items()}
        profile["columns"].append(info)

    return profile


def format_profile(profile: dict) -> str:
    """Format a profile dict as a readable string for LLM input."""
    lines = [
        f"Rows: {profile['row_count']}  |  Columns: {profile['col_count']}",
        f"Duplicates: {profile['duplicate_rows']}  |  Total missing: {profile['missing_total']}",
        "",
    ]
    for col in profile["columns"]:
        lines.append(f"--- {col['name']} ({col['dtype']}) ---")
        lines.append(f"  nulls: {col['null_count']} ({col['null_pct']}%)")
        lines.append(f"  unique: {col['unique_count']}")
        if "mean" in col:
            lines.append(f"  range: [{col['min']}, {col['max']}]  median={col['median']}  mean={col['mean']}  std={col['std']}")
            if col["outlier_pct"] > 0:
                lines.append(f"  outliers: {col['outlier_pct']}%")
        if "top_values" in col:
            top = ", ".join(f"{k}: {v}" for k, v in col["top_values"].items())
            lines.append(f"  top: {top}")
        lines.append("")
    return "\n".join(lines)


def save_profile_tables(df: pd.DataFrame, profile: dict, out_dir: Path) -> list[str]:
    """Save meta-analytics tables as CSVs for researcher inspection.

    These are decision-support tables (not publication charts):
    - numeric_summary.csv: distributions, skew, outliers, scaling needs
    - value_counts.csv: full frequency table per column (like data.gov.sg data explorer)
    - correlations.csv: pairwise correlation matrix
    - column_assessment.csv: per-column strategy recommendations
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    n = len(df)

    # 1. Numeric summary
    numeric_cols = profile["numeric_cols"]
    if numeric_cols:
        rows = []
        for col_info in profile["columns"]:
            if "mean" not in col_info:
                continue
            col = col_info["name"]
            s = df[col].dropna()
            skew_val = round(float(s.skew()), 2) if len(s) > 2 else None
            rows.append({
                "column": col,
                "dtype": col_info["dtype"],
                "nulls": col_info["null_count"],
                "null_pct": col_info["null_pct"],
                "unique": col_info["unique_count"],
                "min": col_info["min"],
                "q25": round(float(s.quantile(0.25)), 2) if len(s) else None,
                "median": col_info["median"],
                "q75": round(float(s.quantile(0.75)), 2) if len(s) else None,
                "max": col_info["max"],
                "mean": col_info["mean"],
                "std": col_info["std"],
                "skew": skew_val,
                "outlier_pct": col_info.get("outlier_pct", 0),
                "needs_log": "yes" if skew_val and abs(skew_val) > 1.0 else "",
            })
        pd.DataFrame(rows).to_csv(out_dir / "numeric_summary.csv", index=False)
        written.append("numeric_summary.csv")

    # 2. Value counts — top 10 per column + remainder
    # Categorical columns only (numeric columns covered by numeric_summary)
    vc_rows = []
    cat_cols_set = set(profile["categorical_cols"])
    for col in df.columns:
        if col not in cat_cols_set:
            continue
        vc = df[col].value_counts(dropna=False)
        for val, count in vc.head(10).items():
            vc_rows.append({
                "column": col,
                "value": str(val) if pd.notna(val) else "(Null)",
                "count": int(count),
                "pct": round(count / n * 100, 1),
            })
        remaining = len(vc) - 10
        if remaining > 0:
            vc_rows.append({
                "column": col,
                "value": f"({remaining} more)",
                "count": int(vc.iloc[10:].sum()),
                "pct": round(vc.iloc[10:].sum() / n * 100, 1),
            })
    if vc_rows:
        pd.DataFrame(vc_rows).to_csv(out_dir / "value_counts.csv", index=False)
        written.append("value_counts.csv")

    # 3. Correlation matrix (numeric only)
    if len(numeric_cols) >= 2:
        corr = df[numeric_cols].corr().round(3)
        corr.to_csv(out_dir / "correlations.csv")
        written.append("correlations.csv")

    # 4. Column assessment — per-column strategy recommendations
    assess_rows = []
    for col_info in profile["columns"]:
        col = col_info["name"]
        flags = []
        strategies = []

        # Missing data
        if col_info["null_pct"] > 0:
            if col_info["null_pct"] > 50:
                flags.append("majority_missing")
                strategies.append("consider_dropping")
            elif col_info["null_pct"] > 5:
                flags.append("significant_missing")
                strategies.append("impute_median" if "mean" in col_info else "impute_mode")
            else:
                flags.append("minor_missing")
                strategies.append("impute_or_drop_rows")

        # Numeric-specific
        if "mean" in col_info:
            s = df[col].dropna()
            skew_val = float(s.skew()) if len(s) > 2 else 0
            if abs(skew_val) > 1.5:
                flags.append("high_skew")
                strategies.append("log_transform")
            if col_info.get("outlier_pct", 0) > 5:
                flags.append("high_outliers")
                strategies.append("clip_or_winsorize")
            if col_info["unique_count"] == 1:
                flags.append("constant")
                strategies.append("drop_column")
            elif col_info["unique_count"] <= 10:
                flags.append("low_cardinality_numeric")
                strategies.append("treat_as_categorical")

        # Categorical-specific
        if "top_values" in col_info:
            unique = col_info["unique_count"]
            if unique > 100:
                flags.append("high_cardinality")
                strategies.append("group_rare_categories")
            elif unique == 1:
                flags.append("constant")
                strategies.append("drop_column")

            # Class imbalance check
            if col_info["top_values"]:
                top_count = next(iter(col_info["top_values"].values()))
                if top_count / n > 0.8:
                    flags.append("severe_imbalance")
                    strategies.append("stratified_sampling")
                elif top_count / n > 0.5:
                    flags.append("moderate_imbalance")

        # Potential ID / non-predictive columns
        if col_info["unique_count"] == n:
            flags.append("all_unique")
            strategies.append("likely_id_or_key")

        assess_rows.append({
            "column": col,
            "dtype": col_info["dtype"],
            "unique": col_info["unique_count"],
            "null_pct": col_info["null_pct"],
            "flags": "; ".join(flags) if flags else "clean",
            "suggested_strategy": "; ".join(strategies) if strategies else "none_needed",
        })

    pd.DataFrame(assess_rows).to_csv(out_dir / "column_assessment.csv", index=False)
    written.append("column_assessment.csv")

    return written
