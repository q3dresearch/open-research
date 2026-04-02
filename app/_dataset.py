"""Dataset viewer — pipeline phase viewer and run launcher."""

import base64
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st

# ── path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.artifacts import ARTIFACTS_DIR, ACTIONS

DATA_DIR = ROOT / "data"
DB_PATH  = ROOT / "observatory.db"

# ── phase display config ─────────────────────────────────────────────────────
PHASE_META = {
    "10": {"label": "EDA",        "icon": "🔍"},
    "15": {"label": "Clean",      "icon": "🧹"},
    "20": {"label": "Engineer",   "icon": "⚙️"},
    "25": {"label": "Cluster",    "icon": "🗂️"},
    "30": {"label": "Select",     "icon": "🎯"},
    "50": {"label": "Report",     "icon": "📄"},
}

VENV_PYTHON = ROOT / ".venv" / "bin" / "python"

# phase code → (agent module, label, prerequisite codes)
PHASE_AGENTS = {
    "10": ("agents.analyst",      "Run EDA",          []),
    "15": ("agents.cleaner",      "Run Clean",        ["10"]),
    "20": ("agents.deep_analyst", "Run Engineer",     ["15"]),
    "25": ("agents.clusterer",    "Run Cluster",      ["20"]),
    "30": ("agents.selector",     "Run Select",       ["25"]),
    "50": ("agents.reporter",     "Run Report",       ["30"]),
}

LOCAL_PORTAL_ID = "local-upload"


# ── helpers ──────────────────────────────────────────────────────────────────

def _ensure_local_portal(conn: sqlite3.Connection):
    conn.execute(
        "INSERT OR IGNORE INTO portals (id, url, name, api_type) VALUES (?, ?, ?, ?)",
        (LOCAL_PORTAL_ID, "local://upload", "Local Upload", "local"),
    )


def register_local_dataset(dataset_id: str, title: str, row_count: int, csv_path: Path):
    """Insert a minimal dataset record for a locally uploaded file."""
    conn = sqlite3.connect(DB_PATH)
    _ensure_local_portal(conn)
    conn.execute(
        """INSERT OR REPLACE INTO datasets
           (id, portal_id, resource_url, title, row_count, format, max_action_code, updated_at)
           VALUES (?, ?, ?, ?, ?, 'CSV', NULL, datetime('now'))""",
        (dataset_id, LOCAL_PORTAL_ID, str(csv_path), title, row_count),
    )
    conn.commit()
    conn.close()
    load_datasets.clear()


def ingest_uploaded_file(uploaded) -> tuple[str, str]:
    """Save an st.file_uploader result to data/. Returns (dataset_id, title)."""
    raw   = uploaded.read()
    stem  = Path(uploaded.name).stem
    did   = "local_" + hashlib.md5(raw).hexdigest()[:12]
    dest  = DATA_DIR / f"{did}.csv"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    full  = pd.read_csv(dest)
    register_local_dataset(did, stem, len(full), dest)
    return did, stem


def ingest_url(url: str) -> tuple[str, str]:
    """Download a CSV from a URL to data/. Returns (dataset_id, title)."""
    with urllib.request.urlopen(url, timeout=30) as resp:
        raw = resp.read()
    stem  = Path(url.rstrip("/").split("/")[-1]).stem or "dataset"
    did   = "local_" + hashlib.md5(raw).hexdigest()[:12]
    dest  = DATA_DIR / f"{did}.csv"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    full  = pd.read_csv(dest)
    register_local_dataset(did, stem, len(full), dest)
    return did, stem


@st.cache_data(ttl=30)
def load_datasets():
    """Read all dataset records from observatory.db."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, row_count, max_action_code, updated_at, pipeline_type "
        "FROM datasets WHERE rejected = 0 ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def scan_artifact_phases(dataset_id: str) -> dict:
    """Return {action_code: [run_dir, ...]} for a dataset's artifact tree."""
    base = ARTIFACTS_DIR / dataset_id
    phases = {}
    if not base.exists():
        return phases
    for code, name in ACTIONS.items():
        phase_dir = base / f"{code}-{name}"
        if not phase_dir.exists():
            continue
        runs = sorted([d for d in phase_dir.iterdir() if d.is_dir() and d.name.startswith("run-")])
        phases[code] = runs
    return phases


def latest_run(runs: list[Path]) -> Path | None:
    return runs[-1] if runs else None


def read_md(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def render_md(path: Path) -> None:
    """Render a markdown file, resolving relative image paths via st.image()."""
    text = read_md(path)
    if not text:
        return
    base_dir = path.parent

    # Strip backtick-wrapped image references: `![alt](path)` → ![alt](path)
    text = re.sub(r'`(!\[[^\]]*\]\([^)]+\))`', r'\1', text)

    IMG_PAT = re.compile(r'!\[([^\]]*)\]\(((?:data:[^)]+|[^)]+\.png))\)')
    parts = IMG_PAT.split(text)

    i = 0
    while i < len(parts):
        segment = parts[i]
        if segment.strip():
            st.markdown(segment)
        i += 1
        if i + 1 < len(parts):
            alt, src = parts[i], parts[i + 1]
            i += 2
            if src.startswith("data:"):
                img_bytes = base64.b64decode(src.split(",", 1)[1])
                st.image(img_bytes, caption=alt or None)
            elif not src.startswith("http"):
                img_path = (base_dir / src).resolve()
                if img_path.exists():
                    st.image(str(img_path), caption=alt or None)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def phase_charts(run_dir: Path) -> list[Path]:
    chart_dir = run_dir / "charts"
    if not chart_dir.exists():
        return []
    return sorted(chart_dir.glob("*.png"))


def phase_tables(run_dir: Path) -> list[Path]:
    table_dir = run_dir / "tables"
    if not table_dir.exists():
        return []
    return sorted(table_dir.glob("*.csv"))


def _load_dotenv(env: dict) -> dict:
    dotenv = ROOT / ".env"
    if not dotenv.exists():
        return env
    for line in dotenv.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k and k not in env:
            env[k] = v.strip()
    return env


def run_agent(dataset_id: str, module: str, log_placeholder) -> tuple[bool, list[str]]:
    """Run an agent module as subprocess, streaming stdout into log_placeholder."""
    import os
    env = _load_dotenv({**os.environ})
    if st.session_state.get("api_key"):
        env["OPENROUTER_API_KEY"] = st.session_state["api_key"]

    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", module, dataset_id],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    lines: list[str] = []
    for line in proc.stdout:
        lines.append(line.rstrip())
        log_placeholder.code("\n".join(lines[-80:]), language="text")
    proc.wait()
    load_datasets.clear()
    return proc.returncode == 0, lines


# ── sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    # API key
    st.subheader("Configuration")
    with st.expander("🔑 API Keys", expanded=False):
        api_key = st.text_input(
            "OpenRouter API Key",
            type="password",
            value=st.session_state.get("api_key", ""),
            help="Used by pipeline agents. Stored in session only.",
        )
        if api_key:
            st.session_state["api_key"] = api_key
            st.success("Key set", icon="✅")

    # Add data
    with st.expander("➕ Add data", expanded=False):
        add_tab_file, add_tab_url = st.tabs(["Upload CSV", "URL"])

        with add_tab_file:
            uploaded = st.file_uploader("CSV file", type=["csv"], label_visibility="collapsed")
            if uploaded and st.button("Add", key="btn_upload"):
                with st.spinner("Saving…"):
                    try:
                        did, title = ingest_uploaded_file(uploaded)
                        st.session_state["main_data"] = did
                        st.success(f"Added **{title}**")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

        with add_tab_url:
            url_input = st.text_input("Direct CSV URL", placeholder="https://…/file.csv",
                                      label_visibility="collapsed")
            if url_input and st.button("Fetch", key="btn_url"):
                with st.spinner("Downloading…"):
                    try:
                        did, title = ingest_url(url_input)
                        st.session_state["main_data"] = did
                        st.success(f"Added **{title}**")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    st.divider()

    # Dataset picker
    datasets = load_datasets()

    local_csvs = {p.stem for p in DATA_DIR.glob("*.csv")} if DATA_DIR.exists() else set()
    db_ids     = {d["id"] for d in datasets}
    orphan_ids = local_csvs - db_ids
    options    = [d["id"] for d in datasets] + sorted(orphan_ids)

    def _label(did):
        match = next((d for d in datasets if d["id"] == did), None)
        if match:
            title = (match["title"] or did)[:40]
            code  = match.get("max_action_code") or "—"
            phase = PHASE_META.get(code, {}).get("label", code)
            return f"{title}  [{phase}]"
        return f"{did[:20]}…  [local only]"

    if not options:
        st.info("No datasets found.\nDrop a CSV into `data/` to begin.")
        selected_id = None
    else:
        selected_id = st.selectbox(
            "Dataset",
            options,
            format_func=_label,
            index=0,
            key="main_data",
        )

    if selected_id:
        match = next((d for d in datasets if d["id"] == selected_id), None)
        if match:
            ptype = match.get("pipeline_type") or "transactional"
            ptype_color = {"transactional": "🟢", "aggregate": "🟡", "reference": "🔵"}.get(ptype, "⚪")
            st.caption(
                f"**{match['row_count']:,}** rows · updated {match['updated_at'][:10]}\n\n"
                f"{ptype_color} `{ptype}`"
            )

    st.divider()

    # Phase navigation + run buttons
    if selected_id:
        phases_sb = scan_artifact_phases(selected_id)
        st.markdown("**Pipeline**")
        for code in sorted(PHASE_META):
            meta     = PHASE_META[code]
            done     = code in phases_sb
            runs_sb  = phases_sb.get(code, [])
            badge    = f"  `{len(runs_sb)}✓`" if done else ""
            prereqs  = PHASE_AGENTS[code][2]
            ready    = all(p in phases_sb for p in prereqs)
            row      = st.columns([3, 2])
            row[0].markdown(f"{'✅' if done else '⬜'} {meta['icon']} **{meta['label']}**{badge}")
            btn_label    = "Re-run" if done else "Run"
            btn_disabled = not ready or st.session_state.get(f"running_{code}", False)
            if row[1].button(btn_label, key=f"btn_{code}", disabled=btn_disabled,
                             use_container_width=True):
                st.session_state[f"running_{code}"] = True
                st.session_state["active_run"] = (selected_id, code)
                st.rerun()


# ── main content ──────────────────────────────────────────────────────────────

if not selected_id:
    st.info("No datasets found. Use **Add data** in the sidebar or drop a CSV into `data/`.")
    st.stop()

phases = scan_artifact_phases(selected_id)

# Title row
ds_meta = next((d for d in datasets if d["id"] == selected_id), None)
title   = ds_meta["title"] if ds_meta else selected_id
st.title(title)

# ── Active pipeline run ──────────────────────────────────────────────────────
active = st.session_state.get("active_run")
if active and active[0] == selected_id:
    run_ds_id, run_code = active
    module, run_label, _ = PHASE_AGENTS[run_code]
    st.markdown(f"### ⏳ {run_label}…")
    log_box = st.empty()
    with st.spinner(f"Running {run_label}…"):
        ok, log_lines = run_agent(run_ds_id, module, log_box)
    st.session_state.pop("active_run", None)
    st.session_state.pop(f"running_{run_code}", None)
    if ok:
        st.session_state.pop("last_run_error", None)
        st.success(f"{run_label} complete.")
        time.sleep(0.5)
        st.rerun()
    else:
        st.session_state["last_run_error"] = (run_label, log_lines)
        st.stop()

# ── Persistent error from last failed run ────────────────────────────────────
if "last_run_error" in st.session_state:
    err_label, err_lines = st.session_state["last_run_error"]
    st.error(f"**{err_label} failed.** Review the log below, then retry from the sidebar.")
    st.code("\n".join(err_lines), language="text")
    if st.button("Dismiss", key="dismiss_error"):
        st.session_state.pop("last_run_error", None)
        st.rerun()
    st.divider()

if not phases:
    st.info("No pipeline runs yet. Use the **Run** buttons in the sidebar to start.")
    st.stop()

# ── REPORT (50) — shown first if available ─────────────────────────────────
if "50" in phases:
    run = latest_run(phases["50"])
    md_files = list(run.glob("*.md"))
    meta_file = run / "run_metadata.json"
    meta = read_json(meta_file)

    with st.container():
        st.markdown("## 📄 Report")

        modeling = meta.get("modeling", {})
        tree     = modeling.get("tree", {})
        cols     = st.columns(4)
        cols[0].metric("Rows",        f"{meta.get('row_count', '—'):,}" if meta.get('row_count') else "—")
        cols[1].metric("Features",    meta.get("features_selected", "—"))
        cols[2].metric("Model R²",    f"{tree.get('r2', 0):.4f}" if tree.get("r2") else "—")
        cols[3].metric("Task",        meta.get("task_type", "—"))

        st.divider()

        report_md = next((f for f in md_files if "report" in f.name.lower()), None)
        charts    = phase_charts(run)

        if report_md and charts:
            col_text, col_charts = st.columns([3, 2])
            with col_text:
                render_md(report_md)
            with col_charts:
                for chart in charts:
                    st.image(str(chart), caption=chart.stem.replace("_", " "), width="stretch")
        elif report_md:
            render_md(report_md)
        elif charts:
            for chart in charts:
                st.image(str(chart), width="stretch")

        glossary_path = ARTIFACTS_DIR / selected_id / "50-report" / "glossary.json"
        if glossary_path.exists():
            glossary_data = json.loads(glossary_path.read_text())
            if glossary_data:
                st.divider()
                with st.expander("Column Glossary", expanded=False):
                    df_glossary = pd.DataFrame(glossary_data)
                    col_order = ["column", "origin", "how", "intuition", "selection_outcome", "selection_reason"]
                    df_glossary = df_glossary[[c for c in col_order if c in df_glossary.columns]]
                    st.dataframe(df_glossary, use_container_width=True, hide_index=True)

    st.divider()

# ── PHASE TABS ────────────────────────────────────────────────────────────────
phase_codes = [c for c in sorted(PHASE_META) if c in phases and c != "50"]
if phase_codes:
    tab_labels = [f"{PHASE_META[c]['icon']} {PHASE_META[c]['label']}" for c in phase_codes]
    tabs = st.tabs(tab_labels)

    for tab, code in zip(tabs, phase_codes):
        with tab:
            runs = phases[code]
            run  = latest_run(runs)

            if len(runs) > 1:
                run_names = [r.name for r in runs]
                chosen    = st.selectbox("Run", run_names, index=len(run_names) - 1,
                                         key=f"run_{code}")
                run = next(r for r in runs if r.name == chosen)

            # ── EDA ──────────────────────────────────────────────────────
            if code == "10":
                tables = phase_tables(run)
                charts = phase_charts(run)

                if tables:
                    tnames = [t.stem.replace("_", " ").title() for t in tables]
                    ttabs  = st.tabs(tnames)
                    for ttab, tfile in zip(ttabs, tables):
                        with ttab:
                            st.dataframe(pd.read_csv(tfile), width="stretch")

                if charts:
                    st.markdown("**Charts**")
                    cols = st.columns(2)
                    for i, chart in enumerate(charts):
                        cols[i % 2].image(str(chart), caption=chart.stem.replace("_", " "),
                                          width="stretch")

            # ── CLEAN ────────────────────────────────────────────────────
            elif code == "15":
                clean_dir = ARTIFACTS_DIR / selected_id / "15-clean"
                clean_py  = clean_dir / "clean_pipeline.py"
                md_files  = sorted(clean_dir.glob("*.md")) + (list(run.glob("*.md")) if run else [])
                if md_files:
                    with st.expander("LLM Reasoning", expanded=True):
                        render_md(md_files[0])
                if clean_py.exists():
                    with st.expander("clean_pipeline.py", expanded=False):
                        st.code(clean_py.read_text(), language="python")
                state = read_json(ARTIFACTS_DIR / selected_id / "15-clean" / "state.json")
                if state:
                    c1, c2 = st.columns(2)
                    c1.metric("Rows after clean", f"{state.get('row_count', '—'):,}")
                    c2.metric("Columns", len(state.get("current_columns", [])))
                    if state.get("added_columns"):
                        st.markdown("**Flag columns added:**")
                        st.json(state["added_columns"])

            # ── ENGINEER ─────────────────────────────────────────────────
            elif code == "20":
                md_files = list(run.glob("*.md")) if run else []
                charts   = phase_charts(run) if run else []

                if md_files:
                    with st.expander("Run Narrative", expanded=True):
                        render_md(md_files[0])

                state = read_json(ARTIFACTS_DIR / selected_id / "20-engineer" / "state.json")
                if state:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Rows", f"{state.get('row_count', '—'):,}")
                    c2.metric("Columns", len(state.get("current_columns", [])))
                    c3.metric("Steps applied", state.get("steps_applied", "—"))
                    if state.get("added_columns"):
                        with st.expander("Engineered columns"):
                            st.dataframe(pd.DataFrame(state["added_columns"]), width="stretch")

                eng_py = ARTIFACTS_DIR / selected_id / "20-engineer" / "pipeline.py"
                if eng_py.exists():
                    with st.expander("pipeline.py", expanded=False):
                        st.code(eng_py.read_text(), language="python")

                if charts:
                    st.markdown("**Charts**")
                    cols = st.columns(2)
                    for i, chart in enumerate(charts):
                        cols[i % 2].image(str(chart), caption=chart.stem.replace("_", " "),
                                          width="stretch")

            # ── CLUSTER ──────────────────────────────────────────────────
            elif code == "25":
                cluster_json = read_json(run / "cluster_report.json") if run else {}
                md_files     = list(run.glob("*.md")) if run else []
                charts       = phase_charts(run) if run else []

                if cluster_json:
                    method  = cluster_json.get("best_method", "—")
                    n_clust = cluster_json.get("n_clusters", "—")
                    sil     = cluster_json.get("silhouette", None)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Method", method)
                    c2.metric("Clusters", n_clust)
                    if sil is not None:
                        c3.metric("Silhouette", f"{sil:.4f}")
                    names = cluster_json.get("cluster_names", {})
                    if names:
                        st.markdown("**Cluster names:**  " +
                                    "  ·  ".join(f"`{k}` → {v}" for k, v in names.items()))

                if md_files:
                    with st.expander("LLM Reasoning", expanded=False):
                        render_md(md_files[0])

                if charts:
                    radar = [c for c in charts if "radar" in c.name]
                    hists = [c for c in charts if "histogram" in c.name or c.name.startswith("hist")]
                    other = [c for c in charts if c not in radar and c not in hists]

                    for r in radar:
                        st.image(str(r), caption="Cluster Profiles", width="stretch")
                    if hists:
                        st.markdown("**Feature distributions by cluster**")
                        for h in hists:
                            st.image(str(h), caption=h.stem, width="stretch")
                    if other:
                        cols = st.columns(2)
                        for i, c in enumerate(other):
                            cols[i % 2].image(str(c), caption=c.stem.replace("_", " "),
                                              width="stretch")

            # ── SELECT ───────────────────────────────────────────────────
            elif code == "30":
                feat_report = read_json(run / "feature_report.json") if run else {}
                feat_scores = (run / "feature_scores.csv") if run else Path("/dev/null")
                md_files    = list(run.glob("*.md")) if run else []
                charts      = phase_charts(run) if run else []

                if feat_report:
                    sel     = feat_report.get("selection_report", {})
                    kept    = sel.get("kept", [])
                    dropped = sel.get("dropped", [])
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Features kept", len(kept))
                    c2.metric("Features dropped", len(dropped))
                    c3.metric("Target", feat_report.get("target_col", "—"))

                    with st.expander("Selected features"):
                        st.write(kept)
                    if dropped:
                        with st.expander("Dropped features"):
                            st.dataframe(pd.DataFrame(dropped), width="stretch")

                if feat_scores.exists():
                    with st.expander("Feature scores table"):
                        st.dataframe(pd.read_csv(feat_scores), width="stretch")

                if md_files:
                    with st.expander("LLM Reasoning", expanded=False):
                        render_md(md_files[0])

                if charts:
                    st.markdown("**Selection pipeline charts**")
                    waterfall = [c for c in charts if "waterfall" in c.name]
                    rest      = [c for c in charts if c not in waterfall]
                    for w in waterfall:
                        st.image(str(w), caption="Selection waterfall", width="stretch")
                    if rest:
                        cols = st.columns(2)
                        for i, c in enumerate(rest):
                            cols[i % 2].image(str(c), caption=c.stem.replace("_", " "),
                                              width="stretch")
