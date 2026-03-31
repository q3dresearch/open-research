"""Object registry — named dataframe tracking across pipeline phases.

Inspired by Jupyter's kernel namespace and R's GlobalEnv:
- Every named dataframe gets registered with schema + lineage
- LLMs see the registry when planning steps (not just raw column lists)
- Distinguishes transform objects (column-level) from analysis objects (aggregations)
- Tracks which objects are "alive" vs superseded

Key distinction from pipeline.py (which tracks transforms applied to one df):
- pipeline.py: HOW we got from raw to current state (replay instructions)
- object_registry: WHAT named objects exist right now (LLM environment view)

Stored in artifacts/{dataset_id}/object_registry.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from lib.artifacts import ARTIFACTS_DIR

# Object types
TRANSFORM = "transform"    # Column added/modified in the main df (persists in pipeline.py)
ANALYSIS = "analysis"      # Aggregation/pivot for charts/tables (ephemeral, not in pipeline)
CLUSTER = "cluster"        # Cluster label column (persists in cluster_labels.csv)
SELECTION = "selection"    # Feature selection result (persists in feature_report.json)


def _registry_path(dataset_id: str) -> Path:
    return ARTIFACTS_DIR / dataset_id / "object_registry.json"


def load_registry(dataset_id: str) -> dict:
    """Load object registry. Returns empty registry if not found."""
    path = _registry_path(dataset_id)
    if path.exists():
        return json.loads(path.read_text())
    return {
        "objects": {},
        "execution_log": [],  # like Jupyter's execution_count per cell
    }


def _save(dataset_id: str, registry: dict):
    path = _registry_path(dataset_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, default=str))


def register_object(
    dataset_id: str,
    name: str,
    df: pd.DataFrame,
    *,
    obj_type: str = TRANSFORM,
    created_by: str = "",   # phase + step, e.g. "20-engineer:step_03"
    parent: str = "",       # parent object name, e.g. "rawClean"
    description: str = "",
    run_id: str = "",
):
    """Register a named dataframe in the object registry.

    Args:
        name: object name (e.g. 'rawClean', 'rawAgg', 'df_clustered')
        df: the actual dataframe (only metadata is stored, not data)
        obj_type: TRANSFORM, ANALYSIS, CLUSTER, or SELECTION
        created_by: which phase/step created this
        parent: which object this derives from
        description: human-readable description
    """
    registry = load_registry(dataset_id)
    now = datetime.now(timezone.utc).isoformat()

    # Sample 3 rows for LLM context (like R's str() or Jupyter's df.head())
    try:
        sample = json.loads(df.head(3).to_json(orient="records", date_format="iso"))
        sample_cols = list(df.columns[:8])  # cap at 8 cols for sample
        sample = [{k: r[k] for k in sample_cols if k in r} for r in sample]
    except Exception:
        sample = []

    # Column metadata
    col_meta = {}
    for col in df.columns:
        col_meta[col] = {
            "dtype": str(df[col].dtype),
            "n_unique": int(df[col].nunique()),
            "n_null": int(df[col].isna().sum()),
            "sample_val": str(df[col].dropna().iloc[0]) if not df[col].dropna().empty else None,
        }

    registry["objects"][name] = {
        "type": obj_type,
        "shape": list(df.shape),
        "columns": list(df.columns),
        "col_meta": col_meta,
        "sample_rows": sample,
        "created_by": created_by,
        "parent": parent,
        "description": description,
        "run_id": run_id,
        "created_at": now,
        "alive": True,
    }

    registry["execution_log"].append({
        "action": "register",
        "name": name,
        "type": obj_type,
        "shape": list(df.shape),
        "created_by": created_by,
        "timestamp": now,
    })

    _save(dataset_id, registry)


def retire_object(dataset_id: str, name: str, reason: str = "superseded"):
    """Mark an object as no longer current (like R's rm() but with history)."""
    registry = load_registry(dataset_id)
    if name in registry["objects"]:
        registry["objects"][name]["alive"] = False
        registry["objects"][name]["retired_reason"] = reason
    registry["execution_log"].append({
        "action": "retire",
        "name": name,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save(dataset_id, registry)


def get_alive_objects(dataset_id: str) -> dict:
    """Get all currently alive named objects."""
    registry = load_registry(dataset_id)
    return {k: v for k, v in registry["objects"].items() if v.get("alive", True)}


def format_registry_for_llm(dataset_id: str, max_cols_per_obj: int = 15) -> str:
    """Format the object registry as LLM-readable context.

    Like Jupyter's 'whos' / R's ls() + str() — gives the LLM a view of
    what named objects currently exist and what they contain.
    """
    alive = get_alive_objects(dataset_id)
    if not alive:
        return "(no named objects registered yet)"

    lines = [f"## Active objects ({len(alive)} total)\n"]

    for name, obj in alive.items():
        shape = obj.get("shape", ["?", "?"])
        obj_type = obj.get("type", "?")
        created_by = obj.get("created_by", "?")
        parent = obj.get("parent", "")
        desc = obj.get("description", "")

        lineage = f" ← {parent}" if parent else ""
        lines.append(f"### `{name}` ({obj_type}){lineage}")
        lines.append(f"Shape: {shape[0]:,} rows × {shape[1]} cols | created by: {created_by}")
        if desc:
            lines.append(f"Description: {desc}")

        # Column list (capped)
        cols = obj.get("columns", [])
        shown_cols = cols[:max_cols_per_obj]
        col_meta = obj.get("col_meta", {})
        col_lines = []
        for col in shown_cols:
            meta = col_meta.get(col, {})
            dtype = meta.get("dtype", "?")
            n_null = meta.get("n_null", 0)
            sample = meta.get("sample_val", "")
            null_str = f" {n_null} nulls" if n_null else ""
            col_lines.append(f"  - {col} ({dtype}){null_str} e.g. {str(sample)[:30]}")
        lines.extend(col_lines)
        if len(cols) > max_cols_per_obj:
            lines.append(f"  ... +{len(cols) - max_cols_per_obj} more cols")

        # Sample rows
        sample_rows = obj.get("sample_rows", [])
        if sample_rows:
            lines.append(f"Sample (3 rows): {json.dumps(sample_rows[0])[:120]}...")

        lines.append("")

    return "\n".join(lines)


def print_registry(dataset_id: str):
    """Print object registry to stdout (like Jupyter's variable inspector)."""
    alive = get_alive_objects(dataset_id)
    if not alive:
        print("(no objects registered)")
        return

    print(f"\n{'='*60}")
    print(f"  Object Registry: {dataset_id[:30]}...")
    print(f"  {len(alive)} live objects")
    print(f"{'='*60}")

    type_icons = {TRANSFORM: "df", ANALYSIS: "ag", CLUSTER: "cl", SELECTION: "fs"}
    for name, obj in alive.items():
        icon = type_icons.get(obj.get("type", ""), "??")
        shape = obj.get("shape", ["?", "?"])
        parent = f" ← {obj['parent']}" if obj.get("parent") else ""
        print(f"  [{icon}] {name:25s} {shape[0]:>8,} × {shape[1]:<4}{parent}")
    print()
