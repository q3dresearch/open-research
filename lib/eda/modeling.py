"""Interpretive modeling — linear and tree-based, with publication-ready charts.

Tier 2 analytics: "what does X do to Y after controlling for everything else?"
Unlike features.py (which scores features for selection), this module fits
models for *interpretation* and produces publication-ready summaries and charts.

Linear:  fit_ols → coefficient_plot, partial_residual_plot, interaction_plot
Tree:    fit_tree → confusion_matrix_plot, roc_auc_plot, shap_dependence_plot,
                    tree_feature_importance_plot

Dependencies: statsmodels, lightgbm, shap, sklearn, matplotlib, pandas, numpy
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field


@dataclass
class ModelSummary:
    """Structured output from fit_ols."""
    target: str
    features: list[str]
    log_target: bool
    r_squared: float
    adj_r_squared: float
    n_obs: int
    coefficients: pd.DataFrame  # columns: feature, coef, std_err, t_stat, p_value, ci_lower, ci_upper
    residuals: np.ndarray
    fitted_values: np.ndarray
    aic: float
    bic: float


@dataclass
class TreeModelSummary:
    """Structured output from fit_tree."""
    target: str
    features: list[str]
    task: str  # "classify" or "regress"
    model: object  # fitted LightGBM model
    X_test: pd.DataFrame
    y_test: pd.Series
    y_pred: np.ndarray
    y_prob: np.ndarray | None  # class probabilities (classification only)
    feature_importance: pd.DataFrame  # columns: feature, importance
    n_train: int
    n_test: int
    metric_name: str  # "accuracy"/"f1" for classify, "rmse"/"r2" for regress
    metric_value: float


def fit_ols(df: pd.DataFrame, target: str, features: list[str],
            log_target: bool = False, drop_na: bool = True) -> ModelSummary:
    """Fit OLS regression and return interpretive summary.

    Args:
        df: DataFrame with target and feature columns.
        target: Target column name.
        features: List of feature column names (numeric or dummified categoricals).
        log_target: If True, apply log1p to target before fitting.
        drop_na: If True, drop rows with NaN in any model column.

    Returns:
        ModelSummary with coefficients, fit stats, residuals.
    """
    import statsmodels.api as sm

    model_df = df[[target] + features].copy()
    if drop_na:
        model_df = model_df.dropna()

    # Sample for performance — OLS on >50K rows is slow and rarely changes conclusions
    if len(model_df) > 50000:
        model_df = model_df.sample(50000, random_state=42)

    y = model_df[target]
    if log_target:
        y = np.log1p(y)

    # Dummify categoricals
    X = model_df[features]
    cat_cols = X.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        X = pd.get_dummies(X, columns=cat_cols, drop_first=True, dtype=float)

    X = sm.add_constant(X)
    result = sm.OLS(y, X).fit()

    coef_df = pd.DataFrame({
        "feature": result.params.index.tolist(),
        "coef": result.params.values,
        "std_err": result.bse.values,
        "t_stat": result.tvalues.values,
        "p_value": result.pvalues.values,
        "ci_lower": result.conf_int()[0].values,
        "ci_upper": result.conf_int()[1].values,
    })

    return ModelSummary(
        target=target,
        features=features,
        log_target=log_target,
        r_squared=result.rsquared,
        adj_r_squared=result.rsquared_adj,
        n_obs=int(result.nobs),
        coefficients=coef_df,
        residuals=result.resid.values,
        fitted_values=result.fittedvalues.values,
        aic=result.aic,
        bic=result.bic,
    )


def coefficient_plot(summary: ModelSummary, exclude_const: bool = True,
                     top_n: int = 20, figsize: tuple = (10, 8)):
    """Horizontal coefficient plot with confidence intervals.

    Shows: "after controlling all features, a 1-unit change in X does this to Y."
    """
    import matplotlib.pyplot as plt

    df = summary.coefficients.copy()
    if exclude_const:
        df = df[df["feature"] != "const"]

    # Sort by absolute coefficient, take top N
    df = df.reindex(df["coef"].abs().sort_values(ascending=True).tail(top_n).index)

    fig, ax = plt.subplots(figsize=figsize)
    colors = ["#2196F3" if c > 0 else "#F44336" for c in df["coef"]]
    ax.barh(df["feature"], df["coef"], color=colors, alpha=0.7, height=0.6)
    ax.errorbar(df["coef"], df["feature"],
                xerr=[df["coef"] - df["ci_lower"], df["ci_upper"] - df["coef"]],
                fmt="none", ecolor="gray", capsize=3)
    ax.axvline(0, color="black", linewidth=0.8)

    target_label = f"log({summary.target})" if summary.log_target else summary.target
    ax.set_xlabel(f"Effect on {target_label}")
    ax.set_title(f"OLS Coefficients — {target_label} (R²={summary.r_squared:.3f}, n={summary.n_obs:,})")
    plt.tight_layout()

    desc = (f"Coefficient plot: {len(df)} features, R²={summary.r_squared:.3f}. "
            f"Blue=positive, red=negative effect on {target_label}")
    return fig, desc


def partial_residual_plot(df: pd.DataFrame, summary: ModelSummary,
                          feature: str, max_rows: int = 20000,
                          figsize: tuple = (8, 6)):
    """Partial residual (added variable) plot for a single feature.

    Shows the "true" relationship between feature and target after removing
    the effects of all other features. Useful for detecting non-linearity.
    Samples to max_rows for performance (LOWESS is O(n²)).
    """
    import matplotlib.pyplot as plt
    import statsmodels.api as sm

    model_df = df[[summary.target] + summary.features].dropna().copy()
    if len(model_df) > max_rows:
        model_df = model_df.sample(max_rows, random_state=42)
    y = model_df[summary.target]
    if summary.log_target:
        y = np.log1p(y)

    all_features = summary.features.copy()
    other_features = [f for f in all_features if f != feature]

    # Dummify categoricals for others
    X_others = model_df[other_features]
    cat_cols = X_others.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        X_others = pd.get_dummies(X_others, columns=cat_cols, drop_first=True, dtype=float)
    X_others = sm.add_constant(X_others)

    # Residualize Y on others
    y_resid = sm.OLS(y, X_others).fit().resid

    # Residualize feature on others
    x_vals = model_df[feature]
    if pd.api.types.is_numeric_dtype(x_vals):
        x_resid = sm.OLS(x_vals, X_others).fit().resid
    else:
        # For categorical feature, just use y_resid grouped
        fig, ax = plt.subplots(figsize=figsize)
        grouped = pd.DataFrame({"y_resid": y_resid, feature: model_df[feature].values})
        grouped.boxplot(column="y_resid", by=feature, ax=ax)
        ax.set_title(f"Partial residuals of {summary.target} by {feature}")
        ax.set_xlabel(feature)
        target_label = f"log({summary.target})" if summary.log_target else summary.target
        ax.set_ylabel(f"Residual {target_label}")
        plt.suptitle("")
        plt.tight_layout()
        desc = f"Partial residual boxplot: {summary.target} by {feature}, controlling for {len(other_features)} features"
        return fig, desc

    fig, ax = plt.subplots(figsize=figsize)
    ax.scatter(x_resid, y_resid, alpha=0.05, s=8, color="#2196F3")

    # Add lowess trend
    try:
        from statsmodels.nonparametric.smoothers_lowess import lowess
        smoothed = lowess(y_resid, x_resid, frac=0.3)
        ax.plot(smoothed[:, 0], smoothed[:, 1], color="#F44336", linewidth=2, label="LOWESS")
        ax.legend()
    except Exception:
        pass

    target_label = f"log({summary.target})" if summary.log_target else summary.target
    ax.set_xlabel(f"e({feature} | others)")
    ax.set_ylabel(f"e({target_label} | others)")
    ax.set_title(f"Partial Residual: {feature} → {target_label}")
    plt.tight_layout()

    desc = f"Partial residual plot: {feature} effect on {target_label}, controlling for {len(other_features)} features"
    return fig, desc


def interaction_plot(df: pd.DataFrame, summary: ModelSummary,
                     x_feature: str, group_feature: str,
                     n_groups: int = 4, figsize: tuple = (10, 7)):
    """Interaction plot: how x_feature's effect on Y differs by group.

    For numeric group_feature, creates quantile bins.
    Shows: "x1's effect on log(Y) differs depending on category."
    """
    import matplotlib.pyplot as plt
    import statsmodels.api as sm

    model_df = df[[summary.target] + summary.features].dropna().copy()
    y = model_df[summary.target]
    if summary.log_target:
        y = np.log1p(y)

    # Create groups
    if pd.api.types.is_numeric_dtype(model_df[group_feature]):
        model_df["_group"] = pd.qcut(model_df[group_feature], q=n_groups,
                                      duplicates="drop").astype(str)
    else:
        top_cats = model_df[group_feature].value_counts().head(n_groups).index
        model_df["_group"] = model_df[group_feature].where(
            model_df[group_feature].isin(top_cats), other="(other)")

    groups = sorted(model_df["_group"].unique())
    other_features = [f for f in summary.features if f not in (x_feature, group_feature)]

    fig, ax = plt.subplots(figsize=figsize)
    cmap = plt.cm.viridis(np.linspace(0.15, 0.85, len(groups)))

    for i, grp in enumerate(groups):
        mask = model_df["_group"] == grp
        sub_y = y[mask]
        sub_x = model_df.loc[mask, x_feature]

        if not pd.api.types.is_numeric_dtype(sub_x) or len(sub_y) < 30:
            continue

        # Bin x for clean lines
        n_bins = min(20, sub_x.nunique())
        bins = pd.qcut(sub_x, q=n_bins, duplicates="drop")
        binned = pd.DataFrame({"x": sub_x, "y": sub_y, "bin": bins})
        agg = binned.groupby("bin", observed=True)["y"].median().reset_index()
        agg["x_mid"] = agg["bin"].apply(lambda b: b.mid)
        agg = agg.sort_values("x_mid")

        ax.plot(agg["x_mid"], agg["y"], marker="o", markersize=4,
                color=cmap[i], label=f"{group_feature}={grp}", linewidth=2)

    target_label = f"log({summary.target})" if summary.log_target else summary.target
    ax.set_xlabel(x_feature)
    ax.set_ylabel(f"Median {target_label}")
    ax.set_title(f"Interaction: {x_feature} × {group_feature} → {target_label}")
    ax.legend(fontsize=8)
    plt.tight_layout()

    desc = f"Interaction plot: {x_feature} effect on {target_label} by {group_feature} ({len(groups)} groups)"
    return fig, desc


# ---------------------------------------------------------------------------
# Tree-based modeling (LightGBM)
# ---------------------------------------------------------------------------

def fit_tree(df: pd.DataFrame, target: str, features: list[str],
             task: str = "auto", test_size: float = 0.2,
             log_target: bool = False) -> TreeModelSummary:
    """Fit LightGBM and return evaluation summary.

    Args:
        df: DataFrame with target and feature columns.
        target: Target column name.
        features: List of feature column names.
        task: "classify", "regress", or "auto".
        test_size: Fraction held out for evaluation.
        log_target: If True and task=regress, apply log1p to target.

    Returns:
        TreeModelSummary with model, predictions, metrics.
    """
    from lightgbm import LGBMClassifier, LGBMRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, f1_score, mean_squared_error, r2_score

    model_df = df[[target] + features].dropna().copy()
    y = model_df[target]

    if task == "auto":
        task = "classify" if y.nunique() <= 20 else "regress"

    if task == "regress" and log_target:
        y = np.log1p(y)

    X = model_df[features].copy()
    for c in X.select_dtypes(include=["object", "category"]):
        X[c] = X[c].astype("category")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42)

    if task == "classify":
        model = LGBMClassifier(colsample_bytree=0.8, n_estimators=200, verbose=-1)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test) if hasattr(model, "predict_proba") else None
        metric_name = "f1_weighted"
        metric_value = float(f1_score(y_test, y_pred, average="weighted"))
    else:
        model = LGBMRegressor(colsample_bytree=0.8, n_estimators=200, verbose=-1)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        y_prob = None
        metric_name = "r2"
        metric_value = float(r2_score(y_test, y_pred))

    importance = pd.DataFrame({
        "feature": features,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)

    return TreeModelSummary(
        target=target, features=features, task=task,
        model=model, X_test=X_test, y_test=y_test,
        y_pred=y_pred, y_prob=y_prob,
        feature_importance=importance,
        n_train=len(X_train), n_test=len(X_test),
        metric_name=metric_name, metric_value=metric_value,
    )


def confusion_matrix_plot(summary: TreeModelSummary, figsize: tuple = (8, 7)):
    """Confusion matrix heatmap for classification models."""
    import matplotlib.pyplot as plt
    from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay

    if summary.task != "classify":
        raise ValueError("Confusion matrix only applies to classification tasks")

    labels = sorted(summary.y_test.unique())
    cm = confusion_matrix(summary.y_test, summary.y_pred, labels=labels)

    fig, ax = plt.subplots(figsize=figsize)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=labels)
    disp.plot(ax=ax, cmap="Blues", colorbar=True)
    ax.set_title(f"Confusion Matrix — {summary.target} (F1={summary.metric_value:.3f})")
    plt.tight_layout()

    desc = f"Confusion matrix: {len(labels)} classes, F1={summary.metric_value:.3f}, n_test={summary.n_test}"
    return fig, desc


def roc_auc_plot(summary: TreeModelSummary, figsize: tuple = (8, 7)):
    """ROC curve(s) with AUC for classification models.

    Handles binary and multiclass (one-vs-rest).
    """
    import matplotlib.pyplot as plt
    from sklearn.metrics import roc_curve, auc
    from sklearn.preprocessing import label_binarize

    if summary.task != "classify" or summary.y_prob is None:
        raise ValueError("ROC-AUC requires a classification model with predict_proba")

    labels = sorted(summary.y_test.unique())
    fig, ax = plt.subplots(figsize=figsize)

    if len(labels) == 2:
        # Binary
        fpr, tpr, _ = roc_curve(summary.y_test, summary.y_prob[:, 1], pos_label=labels[1])
        roc_auc = auc(fpr, tpr)
        ax.plot(fpr, tpr, linewidth=2, label=f"AUC = {roc_auc:.3f}")
    else:
        # Multiclass one-vs-rest
        y_bin = label_binarize(summary.y_test, classes=labels)
        for i, label in enumerate(labels):
            if i >= summary.y_prob.shape[1]:
                break
            fpr, tpr, _ = roc_curve(y_bin[:, i], summary.y_prob[:, i])
            roc_auc = auc(fpr, tpr)
            ax.plot(fpr, tpr, linewidth=1.5, label=f"{label} (AUC={roc_auc:.2f})")

    ax.plot([0, 1], [0, 1], "k--", alpha=0.4)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(f"ROC Curve — {summary.target}")
    ax.legend(fontsize=8, loc="lower right")
    plt.tight_layout()

    desc = f"ROC-AUC plot: {len(labels)} classes, n_test={summary.n_test}"
    return fig, desc


def tree_feature_importance_plot(summary: TreeModelSummary, top_n: int = 20,
                                 figsize: tuple = (10, 8)):
    """LightGBM split-based feature importance bar chart."""
    import matplotlib.pyplot as plt

    df = summary.feature_importance.head(top_n).sort_values("importance", ascending=True)

    fig, ax = plt.subplots(figsize=figsize)
    ax.barh(df["feature"], df["importance"], color="#4CAF50", alpha=0.8)
    ax.set_xlabel("Split importance")
    ax.set_title(f"LightGBM Feature Importance — {summary.target} ({summary.metric_name}={summary.metric_value:.3f})")
    plt.tight_layout()

    desc = f"Tree feature importance: top {len(df)} features, {summary.metric_name}={summary.metric_value:.3f}"
    return fig, desc


def shap_dependence_plot(summary: TreeModelSummary, feature: str,
                         interaction_feature: str | None = None,
                         max_samples: int = 5000, figsize: tuple = (9, 6)):
    """SHAP dependence plot for a single feature from the tree model.

    Shows how a feature's SHAP value (marginal contribution) varies
    with its own value, optionally colored by an interaction feature.
    """
    import matplotlib.pyplot as plt
    import shap

    X_sample = summary.X_test
    if len(X_sample) > max_samples:
        X_sample = X_sample.sample(max_samples, random_state=42)

    explainer = shap.TreeExplainer(summary.model)
    shap_values = explainer.shap_values(X_sample)

    # For multiclass, average across classes
    if isinstance(shap_values, list):
        shap_values = np.mean(np.abs(np.array(shap_values)), axis=0)

    feat_idx = list(X_sample.columns).index(feature)
    feat_shap = shap_values[:, feat_idx]
    feat_vals = X_sample[feature].values

    fig, ax = plt.subplots(figsize=figsize)

    if interaction_feature and interaction_feature in X_sample.columns:
        color_vals = X_sample[interaction_feature].values
        if not pd.api.types.is_numeric_dtype(X_sample[interaction_feature]):
            color_vals = pd.Categorical(color_vals).codes.astype(float)
        scatter = ax.scatter(feat_vals, feat_shap, c=color_vals, alpha=0.3, s=10,
                             cmap="coolwarm")
        plt.colorbar(scatter, ax=ax, label=interaction_feature)
    else:
        ax.scatter(feat_vals, feat_shap, alpha=0.3, s=10, color="#2196F3")

    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel(feature)
    ax.set_ylabel(f"SHAP value for {feature}")
    ax.set_title(f"SHAP Dependence: {feature}")
    plt.tight_layout()

    desc = f"SHAP dependence plot: {feature}"
    if interaction_feature:
        desc += f" colored by {interaction_feature}"
    return fig, desc
