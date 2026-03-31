"""Feature analysis — importance, selection, multicollinearity.

Used at engineer (20) and select (30) phases.
Engineer adds columns; select removes low-signal ones based on SHAP,
permutation importance, or VIF before passing to publication.

Dependencies: lightgbm, shap, statsmodels, scikit-learn
"""

import pandas as pd
import numpy as np


def vif_scores(df: pd.DataFrame, nan_threshold: float = 0.2) -> pd.DataFrame:
    """Compute Variance Inflation Factor for numeric columns. [engineer/select]

    High VIF (>5-10) indicates multicollinearity — candidates for removal.
    Requires: statsmodels

    Returns DataFrame with columns: feature, vif
    """
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    numerics = df.select_dtypes(include="number").columns.tolist()
    # Remove high-null columns
    numerics = [c for c in numerics if df[c].isna().mean() < nan_threshold]
    temp = df[numerics].fillna(0)

    vif_data = pd.DataFrame({
        "feature": numerics,
        "vif": [variance_inflation_factor(temp.values, i) for i in range(len(numerics))],
    })
    return vif_data.sort_values("vif", ascending=False)


def shap_importance(df: pd.DataFrame, target: pd.Series,
                    task: str = "auto") -> pd.DataFrame:
    """Compute mean |SHAP| values for each feature. [select]

    Uses LightGBM as the surrogate model. Works for both
    classification (categorical target) and regression (numeric target).
    Requires: lightgbm, shap

    Args:
        df: Feature DataFrame (numeric + categorical ok)
        target: Target series to predict
        task: "classify", "regress", or "auto" (inferred from target)

    Returns DataFrame with columns: feature, mean_abs_shap
    """
    from lightgbm import LGBMClassifier, LGBMRegressor
    import shap

    temp = df.copy()
    for c in temp.select_dtypes(include=["object", "category"]):
        temp[c] = temp[c].astype("category")

    if task == "auto":
        task = "classify" if target.nunique() <= 20 else "regress"

    if task == "classify":
        model = LGBMClassifier(colsample_bytree=0.8, verbose=-1)
    else:
        model = LGBMRegressor(colsample_bytree=0.8, verbose=-1)

    model.fit(temp, target)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(temp)

    # For multiclass, shap_values is a list — average across classes
    if isinstance(shap_values, list):
        shap_values = np.mean([np.abs(sv) for sv in shap_values], axis=0)
    else:
        shap_values = np.abs(shap_values)

    importance = pd.DataFrame({
        "feature": temp.columns.tolist(),
        "mean_abs_shap": shap_values.mean(axis=0),
    })
    return importance.sort_values("mean_abs_shap", ascending=False)


def cv_f1_score(df: pd.DataFrame, target: pd.Series,
                n_splits: int = 5) -> float:
    """Cross-validated weighted F1 score using LightGBM. [select]

    Quick measure of how predictable the target is from current features.
    Requires: lightgbm, scikit-learn
    """
    from lightgbm import LGBMClassifier
    from sklearn.model_selection import cross_val_score

    temp = df.copy()
    for c in temp.select_dtypes(include=["object", "category"]):
        temp[c] = temp[c].astype("category")

    clf = LGBMClassifier(colsample_bytree=0.8, verbose=-1)
    scores = cross_val_score(clf, temp, target, scoring="f1_weighted", cv=n_splits)
    return float(np.mean(scores))


def permutation_importance(df: pd.DataFrame, target: pd.Series,
                           n_repeats: int = 5) -> pd.DataFrame:
    """Permutation importance for feature selection. [select]

    Measures how much predictive performance drops when each feature
    is randomly shuffled. Low importance = candidate for removal.
    Requires: lightgbm, scikit-learn
    """
    from lightgbm import LGBMRegressor, LGBMClassifier
    from sklearn.inspection import permutation_importance as sklearn_pi
    from sklearn.model_selection import train_test_split

    temp = df.copy()
    for c in temp.select_dtypes(include=["object", "category"]):
        temp[c] = temp[c].astype("category")

    is_classify = target.nunique() <= 20
    model_cls = LGBMClassifier if is_classify else LGBMRegressor
    model = model_cls(colsample_bytree=0.8, verbose=-1)

    X_train, X_test, y_train, y_test = train_test_split(temp, target, test_size=0.2, random_state=42)
    model.fit(X_train, y_train)

    result = sklearn_pi(model, X_test, y_test, n_repeats=n_repeats, random_state=42)
    importance = pd.DataFrame({
        "feature": temp.columns.tolist(),
        "importance_mean": result.importances_mean,
        "importance_std": result.importances_std,
    })
    return importance.sort_values("importance_mean", ascending=False)
