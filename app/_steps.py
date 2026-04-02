"""Steps — pipeline phase reference guide."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from lib.db import init_db
from lib.timing import phase_timing_report, format_eta

st.title("📋 Pipeline Steps")
st.caption("Reference guide for each phase — what it does, what it produces, how to run it.")

# ── Timing data from DB ────────────────────────────────────────────────────────
@st.cache_data(ttl=120, max_entries=1)
def get_timing():
    conn = init_db()
    report = phase_timing_report(conn)
    conn.close()
    return report

timing = get_timing()

# ── Phase definitions ──────────────────────────────────────────────────────────
PHASES = [
    {
        "code": "00",
        "name": "Vet",
        "agent": "agents.vetter",
        "icon": "🔎",
        "input": "dataset ID (from scan_catalog or manual)",
        "output": "Artifact markdown, verdict (pass/fail/hold), pipeline_type classification",
        "description": (
            "Schema and quality gate before any pipeline work. Downloads a 500-row sample, "
            "runs a basic EDA profile, and asks the LLM to judge: Is this dataset coherent? "
            "Is it worth running the full pipeline? What pipeline type fits (transactional / "
            "aggregate / reference)?"
        ),
        "verdicts": {
            "pass": "Dataset enters the pipeline. Promoted to phase 10.",
            "fail": "Rejected. `rejected=1` set in DB. Artifact kept as audit trail.",
            "hold": "Borderline — needs human review of `human-notes.md` before re-running.",
        },
        "tips": [
            "Use `--next` to auto-pick the largest pending CSV from scan_catalog.",
            "Check `human-notes.md` if the LLM misclassifies the pipeline type.",
        ],
    },
    {
        "code": "10",
        "name": "EDA",
        "agent": "agents.analyst",
        "icon": "🔍",
        "input": "Full dataset (downloads if cache is stale)",
        "output": "Profile tables, distribution charts, column assessment JSON",
        "description": (
            "Downloads the full dataset (up to 500 MB limit), runs statistics and charts for "
            "every column, and asks the LLM to assess each column's quality and research value. "
            "The column assessment feeds into all downstream agents."
        ),
        "verdicts": {
            "promote": "Advances to phase 15 (clean).",
            "reject": "Dataset rejected at EDA — typically if data is empty, encrypted, or nonsensical.",
            "hold": "Needs human review.",
        },
        "tips": [
            "If the dataset is >500 MB estimated, EDA halts and marks `rejected=too_large`.",
            "Edit `human-notes.md` to hint at which columns matter most.",
        ],
    },
    {
        "code": "15",
        "name": "Clean",
        "agent": "agents.cleaner",
        "icon": "🧹",
        "input": "Raw CSV",
        "output": "`15-clean/clean_pipeline.py` — re-runnable cleaning script",
        "description": (
            "Separates cleaning from engineering. The LLM proposes a list of cleaning "
            "operations (parse types, handle missing, flag outliers, drop junk columns), "
            "then executes them in order, producing a `clean_pipeline.py` that is replayed "
            "by every downstream agent."
        ),
        "verdicts": {
            "clean": "Advances to phase 20.",
            "reject": "Rejected — data too corrupted to clean.",
        },
        "tips": [
            "The cleaner replays the pipeline in-memory — no new CSV is written.",
            "Outlier flags are added as boolean columns, not dropped.",
        ],
    },
    {
        "code": "20",
        "name": "Engineer",
        "agent": "agents.deep_analyst",
        "icon": "⚙️",
        "input": "Clean data (via clean_pipeline.py replay)",
        "output": "`20-engineer/pipeline.py` — feature engineering script",
        "description": (
            "Multi-run investigation architecture. Each run tests one hypothesis "
            "(e.g. 'remaining lease years drives price decay non-linearly'). The LLM "
            "plans steps, executes them via code, evaluates the run, then plans the next "
            "hypothesis. Stops after `--max-runs` (default 3) or when it declares `done`."
        ),
        "verdicts": {
            "continue": "More runs planned — keep calling until done.",
            "done": "Engineer complete. Advances to phase 25.",
        },
        "tips": [
            "Re-run to add more feature hypotheses — pipeline.py accumulates steps.",
            "Set `target: <col>` in human-notes.md to guide hypothesis direction.",
        ],
    },
    {
        "code": "25",
        "name": "Cluster",
        "agent": "agents.clusterer",
        "icon": "🗂️",
        "input": "Engineered data (clean + engineer pipeline replay)",
        "output": "`25-cluster/cluster_labels.csv` — cluster assignment per row",
        "description": (
            "Multi-view clustering: GMM, KPrototypes, and UMAP+HDBSCAN are tried in "
            "parallel. The best view (highest silhouette or DBCV) wins. Regime validation "
            "checks whether clusters are genuine (different slopes) vs noise (different "
            "intercepts only). `cluster_label` is injected as a Track B structural feature."
        ),
        "verdicts": {
            "pass": "Clusters found. `cluster_label` added to features. Advances to phase 30.",
            "no_regime": "No meaningful clusters — continues without cluster feature.",
        },
        "tips": [
            "Silhouette ≥ 0.3 is the quality gate for GMM/KPrototypes.",
            "HDBSCAN uses DBCV; no hard threshold — LLM decides.",
        ],
    },
    {
        "code": "30",
        "name": "Select",
        "agent": "agents.selector",
        "icon": "🎯",
        "input": "Engineered + clustered data",
        "output": "`30-select/feature_report.json` — final feature list + SHAP scores",
        "description": (
            "Six-stage pruning pipeline: missingness → variance → correlation clustering → "
            "MI ranking → SHAP → LLM review. Track A features (predictive) go through all "
            "stages. Track B features (structural: town, flat_type, cluster_label) bypass "
            "pruning. The LLM reviews the final set and can override dropped features."
        ),
        "verdicts": {
            "ready_to_publish": "Advances to phase 50.",
            "needs_more_engineering": "Back to phase 20 for more feature work.",
        },
        "tips": [
            "Mark structural columns in human-notes.md: `structural: [town, flat_type]`",
            "Minimum features to proceed: 3.",
        ],
    },
    {
        "code": "50",
        "name": "Report",
        "agent": "agents.reporter",
        "icon": "📄",
        "input": "Full pipeline state + selected features",
        "output": "`50-report/run-*/report.md` + OLS/LightGBM models + glossary",
        "description": (
            "Generates a dual-layer research report: Layer 1 is a consumer-readable narrative, "
            "Layer 2 is a reproducible audit trail in `<details>` blocks. Also runs OLS and "
            "LightGBM regression, produces SHAP dependence plots, and builds a column glossary "
            "with full lineage for every feature."
        ),
        "verdicts": {
            "complete": "Report written. Dataset at phase 50 (pipeline complete).",
        },
        "tips": [
            "OLS requires a numeric target. LightGBM handles mixed types.",
            "The `session.ipynb` notebook reproduces the full pipeline with COT cells.",
        ],
    },
]

# ── Render phases ──────────────────────────────────────────────────────────────
for phase in PHASES:
    code  = phase["code"]
    t_data = timing.get(phase["name"].lower(), {}) if phase["name"].lower() in timing else \
             timing.get({"Vet": "vet", "EDA": "eda", "Clean": "clean",
                          "Engineer": "engineer", "Cluster": "cluster",
                          "Select": "select", "Report": "report"}[phase["name"]], {})
    eta_str = format_eta(t_data.get("median_s")) if t_data else "—"
    samples = t_data.get("sample_count", 0)

    with st.expander(
        f"{phase['icon']} **{code} — {phase['name']}**  "
        f"`{phase['agent']}`  ·  typical duration {eta_str}"
        + (f"  ({samples} historical runs)" if samples else "  _(no timing data yet)_"),
        expanded=(code == "00"),
    ):
        col_desc, col_meta = st.columns([3, 2])

        with col_desc:
            st.markdown(phase["description"])

            st.markdown("**Verdicts**")
            for verdict, meaning in phase["verdicts"].items():
                st.markdown(f"- `{verdict}` — {meaning}")

            if phase.get("tips"):
                st.markdown("**Tips**")
                for tip in phase["tips"]:
                    st.markdown(f"- {tip}")

        with col_meta:
            st.markdown("**Input**")
            st.caption(phase["input"])
            st.markdown("**Output**")
            st.caption(phase["output"])

            st.markdown("**Run command**")
            st.code(f"python -m {phase['agent']} <dataset_id>", language="bash")

            if t_data:
                st.markdown("**Timing (historical)**")
                st.caption(
                    f"Median: {eta_str} · "
                    f"Median rows: {t_data.get('median_rows', 0):,} · "
                    f"Sample: {samples} runs"
                )

    st.markdown("")

st.markdown("---")
st.subheader("Running the full pipeline")
st.code(
    """# One dataset, all phases
DATASET=d_2d5ff9ea31397b66239f245f57751537

python -m agents.analyst      $DATASET
python -m agents.cleaner      $DATASET
python -m agents.deep_analyst $DATASET
python -m agents.clusterer    $DATASET
python -m agents.selector     $DATASET
python -m agents.reporter     $DATASET
""",
    language="bash",
)

st.subheader("Discovery + batch vetting")
st.code(
    """# Scan next 20 pages of data.gov.sg catalog
python -m agents.discover --pages 20

# Vet one at a time (largest pending CSV first)
python -m agents.vetter --next

# See scan status
python -m agents.discover --status
""",
    language="bash",
)
