---
title: Human Notes
description: How to use human-notes.md to steer AI agents
---

# Human Notes

Every dataset has a `artifacts/{id}/human-notes.md` file. Every agent reads it before acting.

This is your primary steering mechanism — no code changes needed, no prompts to rewrite.

---

## Template

```markdown
# Human Notes: <Dataset Title>

## Target
target: <column_name>

## Structural features (do not drop for low importance)
- feature_name: why it matters

## Better approaches discovered
_(add observations about what worked better for this dataset)_

## Context an agent wouldn't know
_(domain knowledge, policy changes, data quirks)_
```

---

## Sections and their effects

### `## Target`

```markdown
target: resale_price
```

Used by `clusterer.py` and `selector.py` to resolve the prediction target without guessing. Without this, you must pass `--target` on the CLI or rely on prior artifacts.

### `## Structural features`

```markdown
## Structural features (do not drop for low importance)
- price_per_sqm: unit economics, needed for cross-size comparison
- lease_bucket: domain threshold — 60-year cliff is real policy
- town_tier: geographic hierarchy for interaction plots
```

Features listed here are **Track B** — they bypass SHAP/MI pruning at the select phase. The selector LLM is instructed to restore them even if the automated pipeline dropped them.

### `## Better approaches discovered`

Notes about what worked for *this specific dataset*. Agents at engineer phase read this and adjust their hypothesis planning.

```markdown
## Better approaches discovered
- Log-transforming resale_price before OLS improves residual normality significantly
- town_tier interaction with floor_area shows stronger signal than town alone
```

### `## Context an agent wouldn't know`

Domain knowledge the LLM cannot infer from the data alone.

```markdown
## Context an agent wouldn't know
- HDB flats lose value steeply when remaining lease drops below 60 years
- DBSS flats (design, build and sell scheme) are a hybrid public-private category
- Resale levy applies if buyers have previously owned a subsidised flat
```

---

## Human flags

Two flags are set by humans (not agents):

| Flag | How to set | Effect |
|------|-----------|--------|
| `target_declared` | Add `target: col` to human-notes | Clusterer picks it up automatically |
| `structural_features_declared` | Add `## Structural features` section | Selector preserves them |

Set them manually if needed:
```python
from lib.flags import set_flag
set_flag("<dataset_id>", "target_declared", detail="resale_price")
```
