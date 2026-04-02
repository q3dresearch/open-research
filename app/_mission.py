"""Mission Overview — all datasets, phase progress, navigation.

Performance contract:
- Zero filesystem reads. All data comes from observatory.db.
  (max_action_code and runs counts are the source of truth for phase progress.)
- scan_artifact_phases() is NOT called here — only triggered on the dataset
  detail page when a specific dataset is opened.
- The dataset table is a DB query, cached for 30s. Fast even at 1000+ datasets.

Navigating to a dataset: click its row → query param ?dataset=<id> → app.py loads it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from lib.db import init_db

# ── ACTIONS order ────────────────────────────────────────────────────────────
PHASE_ORDER = ["00", "10", "15", "20", "25", "30", "50"]
PHASE_LABELS = {
    "00": "Vet", "10": "EDA", "15": "Clean",
    "20": "Eng", "25": "Clst", "30": "Sel", "50": "Rpt",
}

# ── Load data from DB (zero filesystem) ──────────────────────────────────────
@st.cache_data(ttl=30, max_entries=1)
def load_mission_data():
    conn = init_db()
    rows = conn.execute(
        """
        SELECT d.id, d.title, d.dataset_archetype, d.research_mode, d.max_action_code,
               d.rejected, d.row_count, d.updated_at,
               d.reject_reason,
               (SELECT COUNT(*) FROM runs r WHERE r.dataset_id = d.id) AS run_count
        FROM datasets d
        ORDER BY d.updated_at DESC
        """
    ).fetchall()
    scan_pending = conn.execute(
        "SELECT COUNT(*) FROM scan_catalog WHERE status='pending'"
    ).fetchone()[0]
    scan_total = conn.execute("SELECT COUNT(*) FROM scan_catalog").fetchone()[0]
    conn.close()
    return [dict(r) for r in rows], scan_pending, scan_total


def _phase_bar(max_action_code: str | None, rejected: bool) -> str:
    """Return a compact text progress string like: ✅ ✅ ✅ ⬜ ⬜ ⬜ ⬜"""
    if rejected:
        return "❌ rejected"
    if not max_action_code:
        return "⬜ " * len(PHASE_ORDER)
    chips = []
    for code in PHASE_ORDER:
        if code <= max_action_code:
            chips.append("✅")
        else:
            chips.append("⬜")
    return " ".join(chips)


def _phase_label(max_action_code: str | None, rejected: bool) -> str:
    if rejected:
        return "rejected"
    if not max_action_code:
        return "queued"
    return PHASE_LABELS.get(max_action_code, max_action_code)


# ── Page ──────────────────────────────────────────────────────────────────────
st.title("🗺️ Mission Overview")

rows, scan_pending, scan_total = load_mission_data()

# Summary metrics
total     = len(rows)
active    = sum(1 for r in rows if not r["rejected"] and r["max_action_code"] and r["max_action_code"] > "00")
complete  = sum(1 for r in rows if r["max_action_code"] == "50")
rejected  = sum(1 for r in rows if r["rejected"])
at_vet    = sum(1 for r in rows if not r["rejected"] and r["max_action_code"] == "00")

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total datasets",  total)
c2.metric("At vet (00)",     at_vet)
c3.metric("In pipeline",     active)
c4.metric("Complete",        complete)
c5.metric("Rejected",        rejected)
c6.metric("Pending vet",     scan_pending, help=f"{scan_total} total in catalog")

st.markdown("---")

# ── Filters ───────────────────────────────────────────────────────────────────
fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 3])

with fc1:
    type_filter = st.multiselect(
        "Archetype",
        ["transactional", "panel", "time_series", "aggregate_pivot",
         "aggregate_summary", "cross_section", "reference", "geospatial", "unknown"],
        default=[],
        label_visibility="collapsed",
        placeholder="All archetypes",
    )
with fc2:
    phase_filter = st.multiselect(
        "Phase",
        list(PHASE_LABELS.values()),
        default=[],
        label_visibility="collapsed",
        placeholder="All phases",
    )
with fc3:
    status_filter = st.selectbox(
        "Status",
        ["All", "Active", "Complete", "Rejected", "At vet"],
        label_visibility="collapsed",
    )
with fc4:
    search = st.text_input("Search title", placeholder="Filter by title…",
                           label_visibility="collapsed")

# Apply filters
filtered = rows
if type_filter:
    filtered = [r for r in filtered if r["dataset_archetype"] in type_filter]
if phase_filter:
    filtered = [r for r in filtered if _phase_label(r["max_action_code"], bool(r["rejected"])) in phase_filter]
if status_filter == "Active":
    filtered = [r for r in filtered if not r["rejected"] and r["max_action_code"] and r["max_action_code"] > "00" and r["max_action_code"] != "50"]
elif status_filter == "Complete":
    filtered = [r for r in filtered if r["max_action_code"] == "50"]
elif status_filter == "Rejected":
    filtered = [r for r in filtered if r["rejected"]]
elif status_filter == "At vet":
    filtered = [r for r in filtered if not r["rejected"] and r["max_action_code"] == "00"]
if search:
    q = search.lower()
    filtered = [r for r in filtered if q in (r["title"] or "").lower() or q in r["id"].lower()]

st.caption(f"Showing {len(filtered)} of {total} datasets")
st.markdown("---")

# ── Dataset table ─────────────────────────────────────────────────────────────
PAGE_SIZE = 25
total_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1,
                        label_visibility="collapsed") if total_pages > 1 else 1
page_rows = filtered[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

if total_pages > 1:
    st.caption(f"Page {page} / {total_pages}")

if not page_rows:
    st.info("No datasets match the current filters.")
    st.stop()

# Build display DataFrame
df_display = pd.DataFrame([
    {
        "Title": (r["title"] or r["id"])[:55],
        "Type": r["dataset_archetype"] or "—",
        "Phase": _phase_label(r["max_action_code"], bool(r["rejected"])),
        "Progress": _phase_bar(r["max_action_code"], bool(r["rejected"])),
        "Rows": f"{r['row_count']:,}" if r["row_count"] else "—",
        "Runs": r["run_count"],
        "Updated": (r["updated_at"] or "")[:10],
        "_id": r["id"],
    }
    for r in page_rows
])

# Render as interactive table with row selection
event = st.dataframe(
    df_display.drop(columns=["_id"]),
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Progress": st.column_config.TextColumn("Progress", width="large"),
        "Type": st.column_config.TextColumn("Type", width="small"),
        "Phase": st.column_config.TextColumn("Phase", width="small"),
        "Rows": st.column_config.TextColumn("Rows", width="small"),
        "Runs": st.column_config.NumberColumn("Runs", width="small"),
        "Updated": st.column_config.TextColumn("Updated", width="small"),
    },
)

# Navigate to selected dataset
selected_rows = event.selection.rows if event and hasattr(event, "selection") else []
if selected_rows:
    idx = selected_rows[0]
    selected_id = df_display.iloc[idx]["_id"]
    row = next(r for r in page_rows if r["id"] == selected_id)

    st.markdown("---")
    st.subheader(row["title"] or selected_id)

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Dataset ID", selected_id)
    col_b.metric("Archetype", row["dataset_archetype"] or "unknown")
    col_c.metric("Rows", f"{row['row_count']:,}" if row["row_count"] else "—")

    if row["rejected"]:
        st.error(f"Rejected: {row['reject_reason'] or 'no reason recorded'}")

    st.markdown(f"**Phase progress:** {_phase_bar(row['max_action_code'], bool(row['rejected']))}")
    st.caption(f"Phase codes: " + "  ·  ".join(f"`{c}` {PHASE_LABELS[c]}" for c in PHASE_ORDER))

    st.markdown(
        f"**Open in pipeline viewer →** navigate to the **Dataset** page in the sidebar "
        "and select this dataset from the picker."
    )

# ── Scan catalog summary ──────────────────────────────────────────────────────
with st.expander(f"Scan catalog — {scan_total} total entries", expanded=False):
    @st.cache_data(ttl=60, max_entries=1)
    def load_scan_stats():
        conn = init_db()
        rows = conn.execute(
            """
            SELECT status, format,
                   COUNT(*) cnt,
                   ROUND(AVG(size_bytes)/1024.0/1024, 1) avg_mb
            FROM scan_catalog
            GROUP BY status, format
            ORDER BY status, cnt DESC
            """
        ).fetchall()
        conn.close()
        return pd.DataFrame([dict(r) for r in rows])

    st.dataframe(load_scan_stats(), use_container_width=True, hide_index=True)
