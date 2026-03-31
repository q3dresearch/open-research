"""EDA library — profiling, charts, feature analysis, clustering, time series, modeling.

Module catalog by pipeline phase:
  eda (10):       basic_profile, format_profile, save_profile_tables,
                  generate_eda_charts, cumsum_categories
  engineer (20):  time_series_by_category, seasonality_boxplot, stacked_area_chart,
                  vif_scores
  select (30):    shap_importance, permutation_importance, cv_f1_score,
                  umap_embedding, find_clusters, optimal_cluster_count,
                  ts_prediction_scores
  report (50):    fit_ols, coefficient_plot, partial_residual_plot, interaction_plot,
                  fit_tree, confusion_matrix_plot, roc_auc_plot, shap_dependence_plot
"""

# Always-available (no heavy deps)
from lib.eda.profile import basic_profile, format_profile, save_profile_tables
from lib.eda.charts import generate_eda_charts
from lib.eda.utils import (
    get_numeric_cols, get_categorical_cols, get_nan_cols,
    remove_correlated_cols, remove_constant_cols,
)
