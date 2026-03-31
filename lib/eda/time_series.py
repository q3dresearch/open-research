"""Time series analysis — seasonality, decomposition, lagged prediction.

Used at engineer phase (20) when a temporal column is detected, for trend extraction,
seasonal patterns, and forecasting accuracy tests.

Dependencies: plotly (for interactive), matplotlib (for static PNGs),
              lightgbm + scikit-learn (for ts prediction scoring),
              statsmodels (for VAR)
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ---------------------------------------------------------------------------
# Static (matplotlib) — for pipeline chart output
# ---------------------------------------------------------------------------

def time_series_by_category(df: pd.DataFrame, date_col: str, value_col: str,
                            cat_col: str, agg: str = "mean",
                            top_n: int = 10) -> "tuple[Figure, str]":
    """Line chart of a value over time, one line per category. [engineer]

    Use for: resale price trends by town, revenue by product, etc.
    Static matplotlib output for artifact charts.
    """
    import matplotlib.pyplot as plt

    top_cats = df[cat_col].value_counts().head(top_n).index
    subset = df[df[cat_col].isin(top_cats)].copy()
    subset[date_col] = pd.to_datetime(subset[date_col])

    grouped = subset.groupby([date_col, cat_col])[value_col].agg(agg).reset_index()

    fig, ax = plt.subplots(figsize=(8, 4))
    for cat in top_cats:
        cat_data = grouped[grouped[cat_col] == cat]
        ax.plot(cat_data[date_col], cat_data[value_col], label=str(cat)[:20], linewidth=1)

    ax.legend(fontsize=7, ncol=2, loc="upper left")
    ax.set_title(f"{value_col} by {cat_col}", fontsize=11)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()

    desc = f"Time series: {value_col} ({agg}) by {cat_col}, top {min(top_n, len(top_cats))} categories"
    return fig, desc


def seasonality_boxplot(df: pd.DataFrame, date_col: str, value_col: str,
                        period: str = "month") -> "tuple[Figure, str]":
    """Boxplot of values grouped by time period (month/weekday). [engineer]

    Reveals seasonal patterns — e.g., higher sales in December.
    Static matplotlib output.
    """
    import matplotlib.pyplot as plt

    temp = df.copy()
    temp[date_col] = pd.to_datetime(temp[date_col])

    if period == "month":
        temp["_period"] = temp[date_col].dt.month
        labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    elif period == "weekday":
        temp["_period"] = temp[date_col].dt.weekday
        labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    else:
        temp["_period"] = temp[date_col].dt.quarter
        labels = ["Q1", "Q2", "Q3", "Q4"]

    groups = [temp[temp["_period"] == i][value_col].dropna().values
              for i in range(len(labels))]
    # Filter out empty groups
    valid = [(g, l) for g, l in zip(groups, labels) if len(g) > 0]
    if not valid:
        return None, f"No data for {period} seasonality"

    groups, labels = zip(*valid)

    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.boxplot(groups, labels=labels, patch_artist=True,
               boxprops=dict(facecolor="#4878CF", alpha=0.7),
               medianprops=dict(color="black"))
    ax.set_title(f"{value_col} by {period}", fontsize=11)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()

    desc = f"Seasonality ({period}): {value_col} boxplot across {len(labels)} periods"
    return fig, desc


def stacked_area_chart(df: pd.DataFrame, date_col: str, value_col: str,
                       cat_col: str, normalize: bool = True,
                       top_n: int = 8) -> "tuple[Figure, str]":
    """Stacked area chart showing composition over time. [engineer]

    normalize=True shows percentage contribution (100% stacked).
    Use for: market share evolution, category mix over time.
    """
    import matplotlib.pyplot as plt

    temp = df.copy()
    temp[date_col] = pd.to_datetime(temp[date_col])
    top_cats = temp[cat_col].value_counts().head(top_n).index.tolist()
    temp = temp[temp[cat_col].isin(top_cats)]

    pivot = temp.pivot_table(index=date_col, columns=cat_col,
                             values=value_col, aggfunc="count", fill_value=0)
    pivot = pivot[top_cats]  # maintain order

    if normalize:
        pivot = pivot.div(pivot.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.stackplot(pivot.index, *[pivot[c] for c in pivot.columns],
                 labels=[str(c)[:20] for c in pivot.columns], alpha=0.8)
    ax.legend(fontsize=7, ncol=2, loc="upper left")
    ax.set_title(f"{cat_col} composition over time" + (" (%)" if normalize else ""), fontsize=11)
    ax.tick_params(axis="x", rotation=30)
    if normalize:
        ax.set_ylim(0, 100)
    fig.tight_layout()

    desc = f"Stacked area: {cat_col} {'share' if normalize else 'count'} over {date_col}"
    return fig, desc


# ---------------------------------------------------------------------------
# Analytical (heavy deps) — for select phase hypothesis testing
# ---------------------------------------------------------------------------

def ts_prediction_scores(df: pd.DataFrame, dependent: str, label: str,
                         maxlag: int = 12, n_splits: int = 5,
                         metric: str = "roc") -> list[float]:
    """Lagged prediction accuracy for a time-series feature. [select]

    Tests how well a dependent variable predicts a binary label
    at various lag periods. Uses LightGBM with TimeSeriesSplit CV.
    Requires: lightgbm, scikit-learn

    Returns list of scores, one per lag (1..maxlag).
    """
    from lightgbm import LGBMClassifier
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score

    metric_fn = {"roc": roc_auc_score, "f1": f1_score,
                 "precision": precision_score, "recall": recall_score}[metric]

    temp = df.copy()
    for i in range(1, maxlag + 1):
        temp[f"_lag_{i}"] = temp[dependent].shift(i)
    temp = temp.dropna()

    tscv = TimeSeriesSplit(n_splits=n_splits)
    scores = []

    for lag in range(1, maxlag + 1):
        fold_scores = []
        X = temp[f"_lag_{lag}"].values.reshape(-1, 1)
        y = temp[label].values

        for train_idx, test_idx in tscv.split(X):
            clf = LGBMClassifier(verbose=-1)
            clf.fit(X[train_idx], y[train_idx])
            y_pred = clf.predict(X[test_idx])
            try:
                fold_scores.append(metric_fn(y[test_idx], y_pred))
            except ValueError:
                fold_scores.append(0.5)

        scores.append(float(np.mean(fold_scores)))

    return scores
