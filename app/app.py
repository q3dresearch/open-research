"""q3d Research — Streamlit entrypoint.

Run:
    cd open-research
    .venv/bin/streamlit run app/app.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(
    page_title="q3d Research",
    page_icon=str(ROOT / "assets" / "favicon_package_v0.16" / "favicon-32x32.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Shared sidebar: branding (shown on every page) ───────────────────────────
with st.sidebar:
    _logo_col, _text_col = st.columns([1, 3], vertical_alignment="center")
    _logo_col.image(str(ROOT / "assets" / "qed-mark-black-1500.png"), width=56)
    _text_col.markdown("**Q3D Open Research**\n\nAutonomous AI research pipeline over tabular datasets.")
    st.divider()

# ── Navigation ────────────────────────────────────────────────────────────────
pg = st.navigation(
    {
        "": [st.Page("_home.py", title="Home", icon="🏠", default=True)],
        "Research": [
            st.Page("_dataset.py", title="Dataset", icon="🔬"),
            st.Page("_mission.py", title="Mission", icon="🗺️"),
            st.Page("_steps.py",   title="Steps",   icon="📋"),
        ],
    }
)
pg.run()
