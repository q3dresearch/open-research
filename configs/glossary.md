# Metrics Glossary

Explains every metric produced by the pipeline — who it's for and what it means.

## Feature Scoring Metrics (select phase)

| Metric | What it measures | Audience | Interpretation |
|---|---|---|---|
| `mutual_info` | Non-linear statistical dependency between feature and target | Internal | Higher = more predictive. Scale varies by dataset; compare relative rank, not absolute values |
| `target_corr` | Linear correlation (Pearson) with target variable | Internal | 0–1 (absolute). >0.5 = strong linear signal. Misses non-linear relationships |
| `predictability_r2` | How well OTHER features predict THIS feature (Ridge R²) | Internal | >0.95 = redundant (can be reconstructed from siblings). Yellow zone: 0.8–0.95 |
| `shap` | Mean absolute SHAP value from LightGBM tree model | Internal | Dollar-scale for price targets. Higher = more contribution to predictions. Captures non-linear + interaction effects |

## Column Assessment Flags (eda phase)

| Flag | What it detects | Suggested action |
|---|---|---|
| `needs_log` | Skewness > 1.0 — right-skewed distribution | Apply log1p transform before correlation or modeling |
| `high_cardinality` | >50 unique values in a categorical column | Consider grouping, encoding, or dropping |
| `imbalance` | Top category >80% of values | May dominate models; consider stratified sampling |
| `constant` | Only 1 unique value | Drop — provides no information |
| `high_outliers` | >5% of values beyond 3 standard deviations | Investigate domain meaning before clipping |

## Engineered Column Types

| Type | Purpose | Audience | Example |
|---|---|---|---|
| Raw original | Source data as-is | Consumer | `resale_price`, `town`, `flat_type` |
| Parsed numeric | String → number for analysis | Both | `remaining_lease_years` (from "61 years 04 months") |
| Categorical bucket | Continuous → meaningful groups | Consumer | `lease_status` (short/near_cliff/stable/long) |
| Time components | Datetime → year/month | Both | `year`, `month_num` from `month` YYYY-MM |
| Normalized ratio | Cross-group comparison | Both | `price_per_sqm` — WARNING: leaks target if target is price |
| Log transform | Reduce skew for modeling | Both | `log_resale_price` — for correlation analysis only |
| Geographic index | Location value proxy | Both | `town_valuation_index`, `town_premium_tier` |
| Interaction/derived | Multi-column engineering | Internal | `depreciation_pressure` = (100 - lease) * sensitivity |
| Binary flag | Presence/absence marker | Both | `is_dbss` = 1 if flat_model contains "DBSS" |

### Examples of binary flags (footnotes)

`is_premium_tier_model` = 1 when `flat_model` is one of:
- Premium Apartment
- Premium Maisonette
- Terrace
- Multi Generation

These are HDB flat models that command higher prices due to larger floor area or unique design. They are NOT statistically derived (not percentile-based) — they are categorical labels from HDB's own classification.

`is_dbss` = 1 when `flat_model` contains "DBSS" (Design, Build, Sell Scheme). These were commercially built HDB flats sold at market-adjacent prices. The scheme was discontinued in 2011.

## Selection Stage Descriptions

| Stage | Name | Method | What it removes |
|---|---|---|---|
| S1 | Cheap Prune | Rule-based | >70% missing, near-zero variance, ID-like strings, constants |
| S2 | Correlation Cluster | Hierarchical clustering (avg linkage) | Redundant features correlated >0.85 — keeps highest-variance representative |
| S3 | Pseudo-Target | Ridge regression R² | Features that can be perfectly reconstructed from others (R² > 0.95) |
| S4 | Light Scoring | Mutual info + Pearson correlation | Scores only — doesn't drop by default. LLM decides |
| S5 | SHAP | LightGBM TreeExplainer | Scores only — mean |SHAP| per feature. Expensive but captures non-linear signal |
| S6 | Chart Filter | Heuristic | Retains datetime and low-cardinality categoricals even if low predictive signal |

## Interpretive Modeling Metrics (report phase)

| Metric | What it measures | Audience | Interpretation |
|---|---|---|---|
| `ols_coef` | OLS regression coefficient for feature on log(target) | Consumer | "After controlling all other features, a 1-unit increase in X changes log(Y) by this amount." Sign = direction, magnitude = effect size |
| `p_value` | Statistical significance of the coefficient | Internal | <0.05 = conventionally significant. Large datasets almost always yield small p-values; prefer effect size |
| `partial_residual` | Residual of Y after removing effects of all features except X | Internal | Reveals the "true" shape of X→Y relationship (non-linearity, outliers) after controlling for confounders |
| `interaction_effect` | How X's effect on Y varies across groups of Z | Consumer | If slopes differ across groups, the effect is conditional — e.g., "lease depreciation is steeper in premium towns" |
| `adj_r_squared` | Variance explained by the full model, penalized for number of features | Both | 0–1. Higher = model explains more. Compare across model specifications to judge if adding features helps |
| `confusion_matrix` | Cross-tabulation of predicted vs actual class labels | Consumer | Diagonal = correct. Off-diagonal cells reveal which classes the model confuses |
| `roc_auc` | Area Under ROC Curve — how well the model separates classes across all thresholds | Both | 0.5 = random, 1.0 = perfect. Useful for imbalanced classes where accuracy misleads |
| `shap_dependence` | Per-instance SHAP value for a feature vs that feature's value | Both | Shows the non-linear shape of a feature's marginal contribution. Color by interaction feature to reveal conditional effects |
| `tree_importance` | LightGBM split-based importance — how often a feature is used in tree splits | Internal | High importance ≠ causal. Correlated features split importance. Compare with SHAP for robustness |

### Tier 1 vs Tier 2 analytics

| Tier | What it shows | Example chart | Limitation |
|---|---|---|---|
| Tier 1 (Descriptive) | Unconditional bivariate relationships | "Median price by town" | Confounded — size, floor, lease all vary by town |
| Tier 2 (Predictive) | Conditional effects after controlling for confounders | "Town effect on log(price), holding size/floor/lease constant" | Requires model specification; assumes linearity unless interaction terms added |

## Consumer vs Internal

- **Consumer columns**: Appear in the final report/charts. Must be interpretable without context.
  Examples: `town`, `flat_type`, `resale_price`, `remaining_lease_years`

- **Internal columns**: Used for model training, feature selection, or intermediate analysis. May be dropped before publication.
  Examples: `log_resale_price`, `depreciation_pressure`, `price_residual`, `town_valuation_index`

- **Both**: Useful for analysis AND understandable in reports.
  Examples: `storey_median`, `year`, `lease_status`, `is_dbss`
