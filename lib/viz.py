"""Publication-quality chart functions — generic, column-name-parameterised.

Each function takes explicit column name arguments and returns (fig, description).
The caller is responsible for saving or displaying.

Agents import this to generate analysis charts saved to artifact run dirs.
Notebook cells can also call these directly via importlib or sys.path.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from pathlib import Path


SAVE_KW = {"dpi": 120, "bbox_inches": "tight", "pad_inches": 0.15}


def _save(fig, path):
    fig.savefig(path, **SAVE_KW)
    plt.close(fig)
    return path


def time_series_lines(df, date_col, value_col, cat_col,
                      agg="median", top_n=10):
    """Multi-line time series — one line per category. Publication style."""
    top_cats = df[cat_col].value_counts().head(top_n).index
    subset = df[df[cat_col].isin(top_cats)].copy()
    subset[date_col] = pd.to_datetime(subset[date_col])

    grouped = subset.groupby([pd.Grouper(key=date_col, freq="MS"), cat_col])[value_col] \
        .agg(agg).reset_index()

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = plt.cm.tab10(np.linspace(0, 1, len(top_cats)))
    for cat, color in zip(top_cats, colors):
        cat_data = grouped[grouped[cat_col] == cat].sort_values(date_col)
        ax.plot(cat_data[date_col], cat_data[value_col],
                label=str(cat)[:25], linewidth=1.2, color=color)

    ax.legend(fontsize=7, ncol=2, loc="upper left", framealpha=0.9)
    ax.set_title(f"{agg.title()} {value_col} by {cat_col}", fontsize=12)
    ax.set_ylabel(value_col)
    ax.tick_params(axis="x", rotation=30)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}" if x > 1000 else f"{x:,.1f}"))
    fig.tight_layout()

    return fig, f"Time series: {agg} {value_col} by {cat_col}, {len(top_cats)} categories"


def price_vs_continuous(df, x_col, y_col, n_bins=25):
    """Binned scatter: median y by binned x, with confidence band."""
    data = df[[x_col, y_col]].dropna()
    bins = pd.cut(data[x_col], bins=n_bins)
    grouped = data.groupby(bins, observed=True)[y_col].agg(["median", "mean", "std", "count"])
    grouped = grouped[grouped["count"] >= 5]

    centers = [interval.mid for interval in grouped.index]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(centers, grouped["median"], marker="o", linewidth=2, color="#2196F3",
            markersize=4, label="Median")
    ax.fill_between(centers,
                    grouped["median"] - grouped["std"] * 0.5,
                    grouped["median"] + grouped["std"] * 0.5,
                    alpha=0.15, color="#2196F3", label="±0.5 SD")
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title(f"{y_col} vs {x_col}")
    ax.legend(fontsize=8)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}" if x > 1000 else f"{x:,.1f}"))
    fig.tight_layout()

    return fig, f"Binned scatter: median {y_col} by {x_col}, {len(grouped)} bins"


def storey_gradient(df, price_col, storey_col):
    """Horizontal bar: median price by storey range, heat-colored."""
    grouped = df.groupby(storey_col, observed=True)[price_col].median()
    # Sort by storey range numerically
    try:
        sort_key = grouped.index.map(lambda x: int(str(x).split(" ")[0]))
        grouped = grouped.iloc[sort_key.argsort()]
    except (ValueError, IndexError):
        grouped = grouped.sort_index()

    fig, ax = plt.subplots(figsize=(8, max(3.5, len(grouped) * 0.35)))
    colors = plt.cm.YlOrRd(np.linspace(0.2, 0.9, len(grouped)))
    bars = ax.barh(range(len(grouped)), grouped.values, color=colors)
    ax.set_yticks(range(len(grouped)))
    ax.set_yticklabels(grouped.index, fontsize=8)
    ax.set_xlabel(f"Median {price_col}")
    ax.set_title(f"Median {price_col} by Storey Range")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    fig.tight_layout()

    return fig, f"Storey gradient: {len(grouped)} levels, range ${grouped.min():,.0f}–${grouped.max():,.0f}"


def faceted_boxplots(df, value_col, group_col, hue_col,
                     top_groups=10, top_hues=5):
    """Grouped boxplots: value by group, colored by hue category."""
    top_g = df[group_col].value_counts().head(top_groups).index
    top_h = df[hue_col].value_counts().head(top_hues).index
    subset = df[df[group_col].isin(top_g) & df[hue_col].isin(top_h)]

    colors = plt.cm.Set2(np.linspace(0, 1, len(top_h)))
    n_hues = len(top_h)
    n_groups = len(top_g)

    fig, ax = plt.subplots(figsize=(10, max(5, n_groups * 0.7)))
    y_positions = []
    y_labels = []

    y = 0
    for group in top_g:
        group_center = y + n_hues / 2 - 0.5
        y_positions.append(group_center)
        y_labels.append(str(group)[:25])
        for j, hue in enumerate(top_h):
            data = subset[(subset[group_col] == group) & (subset[hue_col] == hue)][value_col].dropna()
            if len(data) > 0:
                ax.boxplot([data.values], positions=[y], vert=False, widths=0.7,
                           patch_artist=True,
                           boxprops=dict(facecolor=colors[j], alpha=0.7),
                           medianprops=dict(color="black"),
                           flierprops=dict(markersize=1.5, alpha=0.3),
                           whiskerprops=dict(linewidth=0.8))
            y += 1
        y += 1  # gap

    ax.set_yticks(y_positions)
    ax.set_yticklabels(y_labels, fontsize=8)
    ax.set_xlabel(value_col)
    ax.set_title(f"{value_col} by {group_col} × {hue_col}")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}" if x > 1000 else f"{x:,.1f}"))

    from matplotlib.patches import Patch
    legend_patches = [Patch(facecolor=colors[j], label=str(h)[:15]) for j, h in enumerate(top_h)]
    ax.legend(handles=legend_patches, fontsize=7, loc="upper right")
    fig.tight_layout()

    return fig, f"Faceted boxplots: {value_col} by {group_col} × {hue_col}"


def variance_decomposition(df, target_col, factor_cols):
    """Bar chart: fraction of target variance explained by each factor (η²)."""
    y = df[target_col].dropna()
    total_var = y.var()
    results = {}

    for col in factor_cols:
        if col not in df.columns:
            continue
        try:
            if pd.api.types.is_numeric_dtype(df[col]):
                groups = pd.qcut(df[col].dropna(), q=10, duplicates="drop")
                group_means = df.groupby(groups, observed=True)[target_col].transform("mean")
            else:
                group_means = df.groupby(col)[target_col].transform("mean")
            explained = group_means.var() / total_var
            results[col] = min(round(float(explained), 4), 1.0)
        except Exception:
            continue

    if not results:
        return None, "No factors could be decomposed"

    sorted_r = sorted(results.items(), key=lambda x: x[1], reverse=True)
    cols_s, vals_s = zip(*sorted_r)

    fig, ax = plt.subplots(figsize=(8, max(3, len(cols_s) * 0.4)))
    colors = ["#4CAF50" if v > 0.1 else "#FFC107" if v > 0.02 else "#BDBDBD" for v in vals_s]
    ax.barh(range(len(cols_s)), vals_s, color=colors)
    ax.set_yticks(range(len(cols_s)))
    ax.set_yticklabels(cols_s, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Fraction of variance explained (η²)")
    ax.set_title(f"Variance Decomposition: {target_col}")
    for i, v in enumerate(vals_s):
        ax.text(v + 0.005, i, f"{v:.1%}", va="center", fontsize=8)
    fig.tight_layout()

    desc = "Variance decomposition: " + ", ".join(f"{c}={v:.1%}" for c, v in sorted_r[:5])
    return fig, desc


def produce_endgame(df, chart_dir, config):
    """Run all endgame charts for a dataset based on config dict.

    config keys:
        date_col, price_col, cat_cols (list), lease_col, storey_col,
        group_col, hue_col, factor_cols (list)

    Returns list of {"filename": str, "description": str}.
    """
    chart_dir = Path(chart_dir)
    chart_dir.mkdir(parents=True, exist_ok=True)
    results = []

    date_col = config.get("date_col")
    price_col = config.get("price_col", "resale_price")

    # 1. Time series by each categorical
    for cat_col in config.get("cat_cols", []):
        if cat_col in df.columns and date_col in df.columns:
            fig, desc = time_series_lines(df, date_col, price_col, cat_col)
            fname = f"ts_{price_col}_by_{cat_col}.png"
            _save(fig, chart_dir / fname)
            results.append({"filename": fname, "description": desc})

    # 2. Price vs lease (nonlinear cliff)
    lease_col = config.get("lease_col")
    if lease_col and lease_col in df.columns:
        fig, desc = price_vs_continuous(df, lease_col, price_col)
        fname = f"{price_col}_vs_{lease_col}.png"
        _save(fig, chart_dir / fname)
        results.append({"filename": fname, "description": desc})

    # 3. Storey gradient
    storey_col = config.get("storey_col")
    if storey_col and storey_col in df.columns:
        fig, desc = storey_gradient(df, price_col, storey_col)
        fname = f"{price_col}_by_{storey_col}.png"
        _save(fig, chart_dir / fname)
        results.append({"filename": fname, "description": desc})

    # 4. Faceted boxplots
    group_col = config.get("group_col")
    hue_col = config.get("hue_col")
    if group_col and hue_col:
        fig, desc = faceted_boxplots(df, price_col, group_col, hue_col)
        fname = f"boxplot_{price_col}_by_{group_col}_{hue_col}.png"
        _save(fig, chart_dir / fname)
        results.append({"filename": fname, "description": desc})

    # 5. Variance decomposition
    factor_cols = config.get("factor_cols", [])
    if factor_cols:
        fig, desc = variance_decomposition(df, price_col, factor_cols)
        if fig:
            fname = f"variance_decomposition_{price_col}.png"
            _save(fig, chart_dir / fname)
            results.append({"filename": fname, "description": desc})

    return results
