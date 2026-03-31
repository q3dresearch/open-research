"""Chart generation — small, clear PNGs for human viewing and LLM context.

Design principles:
  - Small file size: 100 DPI, tight layout, constrained figsize
  - LLM-readable: clear labels, high contrast, no decoration
  - Each function returns (fig, description) — fig for saving, description for text context
"""

import matplotlib
matplotlib.use("Agg")  # headless backend

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from pathlib import Path

# Minimal style: white bg, no top/right spines, compact
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
})

SAVE_KW = {"dpi": 100, "bbox_inches": "tight", "pad_inches": 0.15}


def _save(fig: plt.Figure, path: Path) -> Path:
    """Save figure and close."""
    fig.savefig(path, **SAVE_KW)
    plt.close(fig)
    return path


def numeric_distributions(df: pd.DataFrame, cols: list[str] | None = None) -> tuple[plt.Figure, str]:
    """Histograms for numeric columns. Returns (fig, text_description)."""
    if cols is None:
        cols = df.select_dtypes(include="number").columns.tolist()
    if not cols:
        return None, "No numeric columns found."

    n = len(cols)
    ncols_grid = min(n, 3)
    nrows = (n + ncols_grid - 1) // ncols_grid
    fig, axes = plt.subplots(nrows, ncols_grid, figsize=(3.2 * ncols_grid, 2.5 * nrows))
    if n == 1:
        axes = [axes]
    else:
        axes = axes.flat if hasattr(axes, "flat") else [axes]

    desc_lines = []
    for i, col in enumerate(cols):
        ax = axes[i]
        data = df[col].dropna()
        ax.hist(data, bins=min(30, max(10, len(data) // 20)), color="#4878CF", edgecolor="white", linewidth=0.5)
        ax.set_title(col)
        ax.xaxis.set_major_locator(mticker.MaxNLocator(5))
        desc_lines.append(f"{col}: median={data.median():.1f}, skew={data.skew():.2f}")

    # Hide unused axes
    for j in range(n, len(list(axes))):
        axes[j].set_visible(False)

    fig.suptitle("Numeric Distributions", fontsize=12, y=1.02)
    fig.tight_layout()
    return fig, "Histograms: " + "; ".join(desc_lines)


def categorical_bars(df: pd.DataFrame, cols: list[str] | None = None, top_n: int = 8) -> tuple[plt.Figure, str]:
    """Horizontal bar charts for categorical columns (top N values)."""
    if cols is None:
        cols = df.select_dtypes(exclude="number").columns.tolist()
    # Filter to columns with reasonable cardinality
    cols = [c for c in cols if 2 <= df[c].nunique() <= 200]
    if not cols:
        return None, "No suitable categorical columns."

    n = len(cols)
    ncols_grid = min(n, 2)
    nrows = (n + ncols_grid - 1) // ncols_grid
    fig, axes = plt.subplots(nrows, ncols_grid, figsize=(4 * ncols_grid, 2 * nrows))
    if n == 1:
        axes = [axes]
    else:
        axes = axes.flat if hasattr(axes, "flat") else [axes]

    desc_lines = []
    for i, col in enumerate(cols):
        ax = axes[i]
        counts = df[col].value_counts().head(top_n)
        ax.barh(counts.index.astype(str)[::-1], counts.values[::-1], color="#4878CF")
        ax.set_title(col)
        desc_lines.append(f"{col}: top={counts.index[0]} ({counts.iloc[0]})")

    for j in range(n, len(list(axes))):
        axes[j].set_visible(False)

    fig.suptitle("Categorical Distributions", fontsize=12, y=1.02)
    fig.tight_layout()
    return fig, "Bar charts: " + "; ".join(desc_lines)


def missing_values_map(df: pd.DataFrame, sample_frac: float = 0.15) -> tuple[plt.Figure, str]:
    """Heatmap showing location of missing values across columns (sampled)."""
    total_missing = df.isna().sum().sum()
    if total_missing == 0:
        return None, "No missing values in dataset."

    sampled = df.sample(frac=min(sample_frac, 1.0), random_state=42) if len(df) > 200 else df
    null_matrix = sampled.isna().T  # columns as rows

    n_cols = len(df.columns)
    fig, ax = plt.subplots(figsize=(6, max(2, 0.35 * n_cols)))
    ax.imshow(null_matrix, aspect="auto", cmap="Blues", interpolation="none")
    ax.set_yticks(range(n_cols))
    ax.set_yticklabels(df.columns)
    ax.set_xlabel(f"Row index (sample of {len(sampled)})")
    ax.set_title("Missing Values Map")

    pcts = (df.isna().mean() * 100).round(1)
    desc = "; ".join(f"{c}: {p}%" for c, p in pcts.items() if p > 0)
    return fig, f"Missing values: {desc}"


def correlation_matrix(df: pd.DataFrame) -> tuple[plt.Figure, str]:
    """Correlation heatmap for numeric columns."""
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if len(num_cols) < 2:
        return None, "Need at least 2 numeric columns for correlation."

    corr = df[num_cols].corr()
    n = len(num_cols)
    fig, ax = plt.subplots(figsize=(max(3, 0.7 * n), max(3, 0.7 * n)))

    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1, aspect="equal")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(num_cols, rotation=45, ha="right")
    ax.set_yticklabels(num_cols)

    # Annotate cells
    for i in range(n):
        for j in range(n):
            val = corr.iloc[i, j]
            color = "white" if abs(val) > 0.6 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7, color=color)

    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Correlation Matrix")
    fig.tight_layout()

    # Describe top correlations
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((num_cols[i], num_cols[j], corr.iloc[i, j]))
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    desc = "; ".join(f"{a}×{b}={r:.2f}" for a, b, r in pairs[:5])
    return fig, f"Top correlations: {desc}"


def boxplots_by_category(df: pd.DataFrame, numeric_col: str, cat_col: str, top_n: int = 10) -> tuple[plt.Figure, str]:
    """Boxplot of a numeric column grouped by a categorical column."""
    top_cats = df[cat_col].value_counts().head(top_n).index
    subset = df[df[cat_col].isin(top_cats)]

    groups = [g[numeric_col].dropna().values for _, g in subset.groupby(cat_col)]
    labels = [str(c) for c in top_cats]

    fig, ax = plt.subplots(figsize=(6, 3))
    bp = ax.boxplot(groups, labels=labels, vert=False, patch_artist=True,
                    boxprops=dict(facecolor="#4878CF", alpha=0.7),
                    medianprops=dict(color="black"))
    ax.set_xlabel(numeric_col)
    ax.set_title(f"{numeric_col} by {cat_col}")
    fig.tight_layout()

    medians = subset.groupby(cat_col)[numeric_col].median().sort_values(ascending=False)
    desc = "; ".join(f"{k}: {v:.0f}" for k, v in medians.head(5).items())
    return fig, f"Medians by {cat_col}: {desc}"


def cumsum_categories(df: pd.DataFrame, cols: list[str] | None = None,
                      top_n: int = 10, max_per_page: int = 10) -> list[tuple[plt.Figure, str]]:
    """Cumulative % bar chart per categorical column. Shows top N + 'Other'.

    Returns list of (fig, description) tuples — one per page of subplots.
    Layout: 5 rows × 2 cols per page.
    """
    if cols is None:
        cols = df.select_dtypes(exclude="number").columns.tolist()
    # Only columns with >1 unique value (skip constants)
    cols = [c for c in cols if df[c].nunique() > 1]
    if not cols:
        return [(None, "No categorical columns for cumsum plot.")]

    pages = []
    desc_all = []

    for page_start in range(0, len(cols), max_per_page):
        page_cols = cols[page_start:page_start + max_per_page]
        n = len(page_cols)
        ncols_grid = min(n, 2)
        nrows = (n + ncols_grid - 1) // ncols_grid
        fig, axes = plt.subplots(nrows, ncols_grid, figsize=(4.5 * ncols_grid, 2.2 * nrows))
        if n == 1:
            axes = [axes]
        else:
            axes = axes.flat if hasattr(axes, "flat") else [axes]

        for i, col in enumerate(page_cols):
            ax = axes[i]
            vc = df[col].value_counts()
            top = vc.head(top_n)
            other_count = vc.iloc[top_n:].sum() if len(vc) > top_n else 0
            other_n = len(vc) - top_n if len(vc) > top_n else 0

            labels = [str(v)[:20] for v in top.index]
            values = list(top.values)
            if other_count > 0:
                labels.append(f"({other_n} others)")
                values.append(other_count)

            total = sum(values)
            pcts = [v / total * 100 for v in values]
            cumsum = []
            running = 0
            for p in pcts:
                running += p
                cumsum.append(running)

            colors = ["#4878CF"] * len(top) + (["#AAAAAA"] if other_count > 0 else [])
            ax.bar(range(len(labels)), pcts, color=colors, edgecolor="white", linewidth=0.5)
            ax.plot(range(len(labels)), cumsum, color="#D04030", marker="o", markersize=3, linewidth=1.2)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
            ax.set_ylabel("%")
            ax.set_title(f"{col} ({df[col].nunique()} unique)", fontsize=9)
            ax.set_ylim(0, 105)

            # Annotate concentration
            top1_pct = pcts[0]
            top3_pct = sum(pcts[:min(3, len(pcts))])
            desc_all.append(f"{col}: {df[col].nunique()} unique, top1={top1_pct:.0f}%, top3={top3_pct:.0f}%")

        for j in range(n, len(list(axes))):
            axes[j].set_visible(False)

        page_idx = page_start // max_per_page + 1
        fig.suptitle(f"Category Distributions (page {page_idx})", fontsize=12, y=1.02)
        fig.tight_layout()
        pages.append((fig, "; ".join(desc_all[page_start:page_start + max_per_page])))

    return pages


def generate_eda_charts(df: pd.DataFrame, chart_dir: Path, profile: dict | None = None) -> list[dict]:
    """Generate standard EDA charts and save to chart_dir.

    Returns list of {"filename": str, "description": str} for each chart.
    """
    chart_dir.mkdir(parents=True, exist_ok=True)
    results = []

    # 1. Numeric distributions
    fig, desc = numeric_distributions(df)
    if fig:
        _save(fig, chart_dir / "numeric_distributions.png")
        results.append({"filename": "numeric_distributions.png", "description": desc})

    # 2. Cumulative category distributions (replaces simple bar charts)
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()
    cat_cols = [c for c in cat_cols if df[c].nunique() > 1]
    if cat_cols:
        pages = cumsum_categories(df, cat_cols)
        for idx, (fig, desc) in enumerate(pages):
            if fig:
                fname = f"category_cumsum_{idx + 1}.png" if len(pages) > 1 else "category_cumsum.png"
                _save(fig, chart_dir / fname)
                results.append({"filename": fname, "description": desc})

    # 3. Missing values
    fig, desc = missing_values_map(df)
    if fig:
        _save(fig, chart_dir / "missing_values.png")
        results.append({"filename": "missing_values.png", "description": desc})
    else:
        results.append({"filename": None, "description": desc})

    # 4. Correlation matrix
    fig, desc = correlation_matrix(df)
    if fig:
        _save(fig, chart_dir / "correlation_matrix.png")
        results.append({"filename": "correlation_matrix.png", "description": desc})

    # 5. Boxplots — if we have a clear numeric target and categorical grouper
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = [c for c in df.select_dtypes(exclude="number").columns if 2 <= df[c].nunique() <= 30]
    if numeric_cols and cat_cols:
        # Pick the numeric col with highest variance, and the cat col with most groups (up to 30)
        target = df[numeric_cols].std().idxmax()
        grouper = max(cat_cols, key=lambda c: df[c].nunique())
        fig, desc = boxplots_by_category(df, target, grouper)
        _save(fig, chart_dir / "boxplot_target.png")
        results.append({"filename": "boxplot_target.png", "description": desc})

    return results
