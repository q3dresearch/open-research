"""Home — welcome, getting-started guide, and philosophy."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st

_, hero, _ = st.columns([1, 3, 1])
with hero:
    logo_col, title_col = st.columns([1, 4], vertical_alignment="center")
    logo_col.image(str(ROOT / "assets" / "qed-mark-black-1500.png"), width=72)
    title_col.markdown("# q3d Open Research")
    st.caption(
        "Autonomous AI research pipeline over public open datasets. "
        "Discovers, vets, cleans, engineers, clusters, and reports — "
        "with a human in the loop at every meaningful decision point."
    )

st.divider()

tab_start, tab_pipeline, tab_about = st.tabs(["Get Started", "How It Works", "About"])

with tab_start:
    st.markdown("### Before you begin")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            "**1. API key**\n\n"
            "Open **API Keys** in the sidebar on the Dataset page and paste your "
            "[OpenRouter](https://openrouter.ai) key.\n\n"
            "Or add it to `.env` in the repo root:\n"
            "```\nOPENROUTER_API_KEY=sk-or-...\n```"
        )
        st.markdown(
            "**2. Add a dataset**\n\n"
            "Use **Add data** on the Dataset page to:\n"
            "- Upload a CSV directly\n"
            "- Paste a `data.gov.sg` dataset ID (e.g. `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`)\n\n"
            "The dataset appears in the picker once ingested."
        )
    with c2:
        st.markdown(
            "**3. Run the pipeline**\n\n"
            "With a dataset selected, click **Run** next to each phase in order:\n\n"
            "| Phase | What happens |\n"
            "|---|---|\n"
            "| EDA | Profile + charts |\n"
            "| Clean | Fix types, handle missing |\n"
            "| Engineer | Feature hypotheses |\n"
            "| Cluster | Regime discovery |\n"
            "| Select | Feature selection |\n"
            "| Report | Full research report |"
        )
        st.markdown(
            "**4. Steer the agent**\n\n"
            "Edit `artifacts/{dataset_id}/human-notes.md` between phases to:\n"
            "- Set the target variable: `target: resale_price`\n"
            "- Mark structural features: `structural: [town, flat_type]`\n"
            "- Add domain context for the LLM"
        )

    st.divider()
    st.markdown("### Tip: reading the report")
    st.markdown(
        "Once the **Report** phase completes, the narrative appears on the Dataset page. "
        "Charts on the right, text on the left. "
        "Expand **Column Glossary** at the bottom for full column lineage — "
        "origin, how each column was made, intuition, and selection outcome.\n\n"
        "The `session.ipynb` notebook in `artifacts/{dataset_id}/` lets you "
        "reproduce every step and inspect the model's chain-of-thought in the `[COT]` cells."
    )

with tab_pipeline:
    st.markdown("### Seven phases")
    st.markdown(
        "Each phase has a dedicated AI agent. The engineer ↔ cluster loop runs until "
        "regimes are validated. Every phase **replays all upstream transforms** from raw CSV "
        "— no cached state is trusted.\n"
    )
    st.markdown(
        "| Code | Phase | Agent | What it produces |\n"
        "|------|-------|-------|------------------|\n"
        "| 00 | **Vet** | `vetter` | Schema quality gate — pass/fail + `pipeline_type` |\n"
        "| 10 | **EDA** | `analyst` | Profile, distribution charts, column assessment |\n"
        "| 15 | **Clean** | `cleaner` | `clean_pipeline.py` — re-runnable type fixes |\n"
        "| 20 | **Engineer** | `deep_analyst` | `pipeline.py` — iterative feature hypotheses |\n"
        "| 25 | **Cluster** | `clusterer` | `cluster_labels.csv` — regime discovery |\n"
        "| 30 | **Select** | `selector` | `feature_report.json` — 6-stage pruning |\n"
        "| 50 | **Report** | `reporter` | `report.md` + OLS/LightGBM + glossary |"
    )
    st.divider()
    st.markdown("### Pipeline types")
    st.markdown(
        "The vetter classifies each dataset at phase 00:\n\n"
        "- 🟢 **transactional** — row-level records, full 7-phase pipeline\n"
        "- 🟡 **aggregate** — summary statistics, lightweight EDA + join proposal\n"
        "- 🔵 **reference** — lookup tables, ingested for joins only\n\n"
        "See [Pipeline Types docs](https://q3dresearch.github.io/open-research/reference/pipeline-types/)."
    )
    st.divider()
    st.markdown("### Memory system")
    st.markdown(
        "Each agent logs its chain-of-thought to `memory/{dataset_id}/{phase}.md` "
        "after every LLM call. This means:\n\n"
        "- Re-running engineer phase 3 knows what runs 1 and 2 tried\n"
        "- The `session.ipynb` shows collapsible `[COT]` cells for every reasoning step\n"
        "- `memory/main/` holds identity files (SOUL.md, AGENTS.md) loaded into every agent\n\n"
        "Artifact index lives at `memory/{dataset_id}/index.json` — a compact map of "
        "every column, table, and chart produced, with one-line summaries."
    )

with tab_about:
    st.markdown("### Philosophy")
    st.markdown(
        "**Honest failures are valuable.** The pipeline is not optimized toward "
        "impressive outputs. Null results and 'no regime structure found' are valid "
        "conclusions. Quality gates (silhouette ≥ 0.3, regime slope p < 0.05) exist "
        "to prevent reporting signal that isn't there.\n\n"
        "**Good decisions over good predictions.** A feature that explains *why* "
        "something happens structurally is preserved even if it adds no predictive power. "
        "Feature selection has two tracks: Track A (predictive, prunable) and "
        "Track B (structural, bypass pruning).\n\n"
        "**Human in the loop.** Agents read `human-notes.md` before acting. "
        "A researcher can steer target variables, flag structural features, and "
        "annotate domain context. Autonomous but not ungoverned.\n\n"
        "**The agent shows its work.** Every LLM call logs its chain-of-thought. "
        "Every column has lineage. Every dropped feature has a reason."
    )
    st.divider()
    st.markdown("### Resources")
    st.markdown(
        "- [Documentation](https://q3dresearch.github.io/open-research)\n"
        "- [GitHub](https://github.com/q3dresearch/open-research)\n"
        "- [Report an issue](https://github.com/q3dresearch/open-research/issues)\n"
        "- [Pipeline Types](https://q3dresearch.github.io/open-research/reference/pipeline-types/)\n"
        "- [Memory System](https://q3dresearch.github.io/open-research/reference/memory/)"
    )
    st.divider()
    st.caption("All data sourced from public open-data portals. Outputs committed to the public repo.")
