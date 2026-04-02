"""Clustering, dimensionality reduction, and regime validation.

Used at cluster phase (25) for unsupervised regime discovery and at select
phase (30) for structure-aware feature selection.

Three clustering strategies, each seeing different shapes of structure:
  1. GMM — elliptical clusters in numeric space (covariance-aware)
  2. KPrototypes — mixed data, but spherical bias (center+mode)
  3. UMAP + HDBSCAN — nonlinear manifold structure, density-based

Regime validation: tests whether clusters define genuine regime differences
(different slopes) vs mere level differences (different intercepts).

Dependencies: umap-learn, hdbscan, kmodes, scikit-learn, statsmodels
"""

import pandas as pd
import numpy as np


def umap_embedding(df: pd.DataFrame, n_components: int = 2) -> np.ndarray:
    """Compute UMAP embedding for mixed-type data. [select]

    Handles numeric (L2 metric) and categorical (Dice metric) columns
    separately, then intersects the graphs with categorical weighting.
    Requires: umap-learn, scikit-learn

    Returns: np.ndarray of shape (n_samples, n_components)
    """
    import umap
    from sklearn.preprocessing import PowerTransformer

    numerical = df.select_dtypes(exclude=["object", "category", "bool"]).fillna(0)
    categorical = df.select_dtypes(include=["object", "category", "bool"])

    # Power-transform numeric columns
    for c in numerical.columns:
        pt = PowerTransformer()
        numerical[c] = pt.fit_transform(numerical[[c]])

    if len(categorical.columns) == 0:
        # Numeric only
        fit = umap.UMAP(n_components=n_components, metric="l2").fit(numerical)
        return fit.embedding_

    # Mixed: intersect numeric and categorical UMAP graphs
    categorical_encoded = pd.get_dummies(categorical)
    cat_weight = len(categorical.columns) / df.shape[1]

    fit_num = umap.UMAP(n_components=n_components, metric="l2").fit(numerical)
    fit_cat = umap.UMAP(n_components=n_components, metric="dice").fit(categorical_encoded)

    intersection = umap.umap_.general_simplicial_set_intersection(
        fit_num.graph_, fit_cat.graph_, weight=cat_weight)
    intersection = umap.umap_.reset_local_connectivity(intersection)

    embedding = umap.umap_.simplicial_set_embedding(
        data=fit_num._raw_data, graph=intersection,
        n_components=n_components,
        initial_alpha=fit_num._initial_alpha,
        a=fit_num._a, b=fit_num._b,
        gamma=fit_num.repulsion_strength,
        negative_sample_rate=fit_num.negative_sample_rate,
        n_epochs=200, init="random", random_state=np.random,
        metric=fit_num.metric, metric_kwds=fit_num._metric_kwds,
        densmap=False, densmap_kwds={}, output_dens=False,
    )
    return embedding[0]


def find_clusters(df: pd.DataFrame, n_clusters: int,
                  method: str = "auto") -> np.ndarray:
    """Cluster rows using KPrototypes (mixed) or GMM (numeric). [select]

    Auto-selects method based on whether categorical columns exist.
    Requires: kmodes (for KPrototypes), scikit-learn (for GMM)

    Returns: np.ndarray of cluster labels
    """
    from sklearn.preprocessing import PowerTransformer

    temp = df.copy()
    cat_cols = temp.select_dtypes(include=["object", "category", "bool"]).columns.tolist()

    # Power-transform numerics
    for c in temp.select_dtypes(exclude=["object", "category", "bool"]).columns:
        pt = PowerTransformer()
        temp[c] = pt.fit_transform(temp[[c]])

    if (method == "auto" and len(cat_cols) > 0) or method == "kprototypes":
        from kmodes.kprototypes import KPrototypes
        cat_idx = [temp.columns.get_loc(c) for c in cat_cols]
        kproto = KPrototypes(n_clusters=n_clusters, init="Cao", n_jobs=4)
        return kproto.fit_predict(temp, categorical=cat_idx)
    else:
        from sklearn.mixture import GaussianMixture
        num_data = temp.select_dtypes(include="number").fillna(0)
        gmm = GaussianMixture(n_components=n_clusters, random_state=42)
        return gmm.fit_predict(num_data)


def optimal_cluster_count(df: pd.DataFrame, max_k: int = 8) -> pd.DataFrame:
    """Evaluate GMM cluster count using BIC and AIC. [select]

    Lower BIC/AIC = better fit. The elbow point suggests optimal k.
    Requires: scikit-learn

    Returns DataFrame with columns: n_clusters, bic, aic
    """
    from sklearn.mixture import GaussianMixture

    num_data = df.select_dtypes(include="number").fillna(0)
    results = []
    for k in range(1, max_k + 1):
        gmm = GaussianMixture(n_components=k, random_state=42).fit(num_data)
        results.append({"n_clusters": k, "bic": gmm.bic(num_data), "aic": gmm.aic(num_data)})
    return pd.DataFrame(results)


def cluster_profile(df: pd.DataFrame, cluster_col: str) -> pd.DataFrame:
    """Compute mean of numeric columns per cluster. [cluster/select]

    Quick summary of what makes each cluster distinct.
    """
    return df.groupby(cluster_col).agg(
        **{c: (c, "mean") for c in df.select_dtypes(include="number").columns
           if c != cluster_col}
    ).round(3)


# ---------------------------------------------------------------------------
# Density-based clustering — captures nonlinear manifold structure
# ---------------------------------------------------------------------------

def density_clusters(df: pd.DataFrame, min_cluster_size: int = 50,
                     use_umap: bool = True) -> tuple[np.ndarray, dict]:
    """HDBSCAN clustering, optionally on UMAP embedding. [cluster]

    HDBSCAN finds clusters of varying density and arbitrary shape.
    Unlike GMM/KMeans, it doesn't force every point into a cluster —
    noise points get label -1.

    Args:
        min_cluster_size: smallest group HDBSCAN will consider a cluster.
        use_umap: if True, cluster in UMAP space (captures nonlinear structure).

    Returns: (labels, info_dict)
    """
    import hdbscan

    if use_umap:
        embedding = umap_embedding(df, n_components=min(5, max(2, len(df.columns) // 3)))
        data = embedding
    else:
        from sklearn.preprocessing import StandardScaler
        num_data = df.select_dtypes(include="number").fillna(0)
        data = StandardScaler().fit_transform(num_data)

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=max(5, min_cluster_size // 5),
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(data)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    noise_pct = (labels == -1).sum() / len(labels)

    return labels, {
        "method": "hdbscan" + ("+umap" if use_umap else ""),
        "n_clusters": n_clusters,
        "noise_pct": round(float(noise_pct), 4),
        "min_cluster_size": min_cluster_size,
    }


def multi_view_cluster(df: pd.DataFrame, max_k: int = 6,
                       target_col: str | None = None) -> list[dict]:
    """Run multiple clustering strategies and compare. [cluster]

    Each method sees different structure:
      - GMM: elliptical, covariance-aware (numeric only)
      - KPrototypes: mixed data, spherical bias
      - UMAP+HDBSCAN: nonlinear manifold, density-based

    Returns a list of view dicts, each with:
      method, labels, n_clusters, silhouette, info
    Sorted by silhouette descending. Caller picks the best or combines.
    """
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    num_data = df.select_dtypes(include="number").fillna(0)
    cat_cols = df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()
    X_scaled = StandardScaler().fit_transform(num_data)

    views = []

    # --- View 1: GMM (elliptical, numeric) ---
    try:
        sil_df = silhouette_analysis(df, max_k=max_k)
        best_row = sil_df.loc[sil_df["silhouette"].idxmax()]
        best_k = int(best_row["n_clusters"])

        from sklearn.mixture import GaussianMixture
        gmm = GaussianMixture(n_components=best_k, random_state=42).fit(X_scaled)
        gmm_labels = gmm.predict(X_scaled)

        views.append({
            "method": "gmm",
            "labels": gmm_labels,
            "n_clusters": best_k,
            "silhouette": round(float(best_row["silhouette"]), 4),
            "info": {"bic": float(best_row["bic"]),
                     "strengths": "elliptical covariance, soft assignment",
                     "weaknesses": "numeric only, assumes Gaussian"},
        })
    except Exception:
        pass

    # --- View 2: KPrototypes (mixed data, if categoricals exist) ---
    if cat_cols:
        try:
            best_k_kp = views[0]["n_clusters"] if views else 3
            kp_labels = find_clusters(df, n_clusters=best_k_kp, method="kprototypes")
            sil_kp = silhouette_score(X_scaled, kp_labels,
                                      sample_size=min(5000, len(X_scaled)))
            views.append({
                "method": "kprototypes",
                "labels": kp_labels,
                "n_clusters": best_k_kp,
                "silhouette": round(float(sil_kp), 4),
                "info": {"strengths": "handles mixed data natively",
                         "weaknesses": "spherical bias, misses nonlinear structure"},
            })
        except Exception:
            pass

    # --- View 3: UMAP + HDBSCAN (nonlinear manifold) ---
    try:
        min_cs = max(50, len(df) // 20)  # at least 5% of data
        hdb_labels, hdb_info = density_clusters(df, min_cluster_size=min_cs,
                                                 use_umap=True)
        # Only score if we got real clusters (not all noise)
        if hdb_info["n_clusters"] >= 2:
            # For silhouette, exclude noise points
            mask = hdb_labels >= 0
            if mask.sum() > 100:
                sil_hdb = silhouette_score(X_scaled[mask], hdb_labels[mask],
                                           sample_size=min(5000, mask.sum()))
            else:
                sil_hdb = 0.0
            views.append({
                "method": "umap_hdbscan",
                "labels": hdb_labels,
                "n_clusters": hdb_info["n_clusters"],
                "silhouette": round(float(sil_hdb), 4),
                "info": {**hdb_info,
                         "strengths": "nonlinear manifold, arbitrary shape, density-aware",
                         "weaknesses": "noise points unassigned, less stable with small data"},
            })
        else:
            views.append({
                "method": "umap_hdbscan",
                "labels": hdb_labels,
                "n_clusters": hdb_info["n_clusters"],
                "silhouette": 0.0,
                "info": {**hdb_info, "note": "no clear density clusters found"},
            })
    except Exception:
        pass

    views.sort(key=lambda v: v["silhouette"], reverse=True)
    return views


# ---------------------------------------------------------------------------
# Cluster quality assessment — used at cluster phase (25)
# ---------------------------------------------------------------------------

def silhouette_analysis(df: pd.DataFrame, max_k: int = 8) -> pd.DataFrame:
    """Evaluate cluster count using silhouette score + BIC. [cluster]

    Silhouette > 0.3 = reasonable structure. Combined with BIC for GMM.
    Returns DataFrame with columns: n_clusters, silhouette, bic, aic
    """
    from sklearn.mixture import GaussianMixture
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    num_data = df.select_dtypes(include="number").fillna(0)
    X = StandardScaler().fit_transform(num_data)

    results = []
    for k in range(2, max_k + 1):
        gmm = GaussianMixture(n_components=k, random_state=42).fit(X)
        labels = gmm.predict(X)
        sil = silhouette_score(X, labels, sample_size=min(5000, len(X)))
        results.append({
            "n_clusters": k,
            "silhouette": round(float(sil), 4),
            "bic": round(float(gmm.bic(X)), 1),
            "aic": round(float(gmm.aic(X)), 1),
        })
    return pd.DataFrame(results)


def validate_cluster_sizes(labels: np.ndarray, min_pct: float = 0.05) -> dict:
    """Check that no cluster is smaller than min_pct of total. [cluster]

    Returns: {"valid": bool, "sizes": {label: pct}, "violations": [labels]}
    """
    total = len(labels)
    unique, counts = np.unique(labels, return_counts=True)
    sizes = {int(u): round(c / total, 4) for u, c in zip(unique, counts)}
    violations = [int(u) for u, c in zip(unique, counts) if c / total < min_pct]
    return {
        "valid": len(violations) == 0,
        "n_clusters": len(unique),
        "sizes": sizes,
        "violations": violations,
    }


def regime_validation(df: pd.DataFrame, target_col: str,
                      feature_cols: list[str], cluster_col: str) -> list[dict]:
    """Test if clusters define genuine regimes via interaction terms. [cluster]

    For each feature, fits: target ~ feature + cluster + feature:cluster
    If the interaction term (feature:cluster) is significant (p < 0.05),
    clusters define different slopes — a genuine regime, not just level shift.

    Returns list of {feature, intercept_p, slope_p, is_regime, f_stat}.
    """
    import statsmodels.api as sm

    results = []
    data = df[[target_col, cluster_col] + feature_cols].dropna()
    if len(data) < 50:
        return results

    cluster_dummies = pd.get_dummies(data[cluster_col], prefix="cl", drop_first=True)

    for feat in feature_cols:
        if not pd.api.types.is_numeric_dtype(data[feat]):
            continue
        try:
            # Full model: target ~ feature + cluster_dummies + feature*cluster_dummies
            interactions = cluster_dummies.multiply(data[feat], axis=0)
            interactions.columns = [f"{feat}_x_{c}" for c in interactions.columns]

            X = pd.concat([
                data[[feat]],
                cluster_dummies,
                interactions,
            ], axis=1).astype(float)
            X = sm.add_constant(X)
            y = data[target_col].astype(float)

            model = sm.OLS(y, X).fit()

            # Test interaction terms jointly (F-test)
            interaction_cols = [c for c in interactions.columns]
            if interaction_cols:
                r_matrix = np.zeros((len(interaction_cols), len(model.params)))
                for i, col in enumerate(interaction_cols):
                    idx = list(model.params.index).index(col)
                    r_matrix[i, idx] = 1
                f_test = model.f_test(r_matrix)
                slope_p = float(f_test.pvalue)
                f_stat = float(f_test.fvalue)
            else:
                slope_p = 1.0
                f_stat = 0.0

            # Test cluster dummies (intercept differences)
            cluster_cols_in_model = [c for c in cluster_dummies.columns if c in model.params.index]
            if cluster_cols_in_model:
                r_matrix_int = np.zeros((len(cluster_cols_in_model), len(model.params)))
                for i, col in enumerate(cluster_cols_in_model):
                    idx = list(model.params.index).index(col)
                    r_matrix_int[i, idx] = 1
                f_test_int = model.f_test(r_matrix_int)
                intercept_p = float(f_test_int.pvalue)
            else:
                intercept_p = 1.0

            results.append({
                "feature": feat,
                "intercept_p": round(intercept_p, 6),
                "slope_p": round(slope_p, 6),
                "is_regime": slope_p < 0.05,
                "f_stat": round(f_stat, 2),
            })
        except Exception:
            continue

    return results


def between_cluster_anova(df: pd.DataFrame, target_col: str,
                          cluster_col: str) -> dict:
    """One-way ANOVA: does target differ significantly across clusters? [cluster]

    Returns: {"f_stat": float, "p_value": float, "eta_squared": float}
    eta_squared = between-group variance / total variance (effect size).
    """
    from scipy import stats

    groups = [g[target_col].dropna().values
              for _, g in df.groupby(cluster_col) if len(g) >= 2]
    if len(groups) < 2:
        return {"f_stat": 0, "p_value": 1.0, "eta_squared": 0}

    f_stat, p_value = stats.f_oneway(*groups)

    # Eta squared
    grand_mean = df[target_col].mean()
    ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups)
    ss_total = ((df[target_col] - grand_mean) ** 2).sum()
    eta_sq = ss_between / ss_total if ss_total > 0 else 0

    return {
        "f_stat": round(float(f_stat), 2),
        "p_value": round(float(p_value), 6),
        "eta_squared": round(float(eta_sq), 4),
    }


def cluster_quality_report(df: pd.DataFrame, labels: np.ndarray,
                           target_col: str, feature_cols: list[str],
                           cluster_col: str = "cluster_label",
                           silhouette: float | None = None) -> dict:
    """Combined cluster quality assessment. [cluster]

    Runs all validation checks and returns a structured report:
    - size_check: cluster size validation
    - anova: between-cluster target differences
    - regime_tests: per-feature regime validation
    - verdict: pass/marginal/fail

    silhouette: best-view silhouette score (included in verdict logic).
    """
    temp = df.copy()
    temp[cluster_col] = labels

    size_check = validate_cluster_sizes(labels)
    anova = between_cluster_anova(temp, target_col, cluster_col)
    regime_tests = regime_validation(temp, target_col, feature_cols, cluster_col)

    # Verdict logic
    n_regimes = sum(1 for r in regime_tests if r["is_regime"])
    has_good_silhouette = silhouette is None or silhouette >= 0.3
    sizes_ok = size_check["valid"]
    anova_sig = anova["p_value"] < 0.05
    has_regimes = n_regimes > 0

    if sizes_ok and has_good_silhouette and anova_sig and has_regimes:
        verdict = "pass"
    elif sizes_ok and (anova_sig or has_regimes):
        verdict = "marginal"
    else:
        verdict = "fail"

    return {
        "verdict": verdict,
        "silhouette": silhouette,
        "size_check": size_check,
        "anova": anova,
        "regime_tests": regime_tests,
        "n_regime_features": n_regimes,
        "n_features_tested": len(regime_tests),
    }
