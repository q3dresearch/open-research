"""Run memory / flag system — VN-style route unlocking.

Each dataset accumulates flags as phases complete. Flags track what has been
discovered, what's been validated, and what routes are unlocked.

Like a visual novel: you need certain flags to unlock routes, and you can
speed-run (skip optional flags) or go for the true ending (all flags).

Flags are stored in `artifacts/{dataset_id}/flags.json`.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from lib.artifacts import ARTIFACTS_DIR, ACTIONS

# ---------------------------------------------------------------------------
# Flag definitions — what each phase can set
# ---------------------------------------------------------------------------

# flag_name → {description, set_by (phase), required_for (list of phases)}
FLAG_CATALOG = {
    # Vet phase
    "schema_vetted": {
        "description": "Dataset schema has been vetted by LLM",
        "set_by": "vet",
        "required_for": ["eda"],
    },

    # EDA phase
    "eda_profiled": {
        "description": "Full EDA profile completed (charts, tables, column assessment)",
        "set_by": "eda",
        "required_for": ["clean"],
    },
    "column_assessment_exists": {
        "description": "Column assessment CSV produced (flags, strategies)",
        "set_by": "eda",
        "required_for": ["clean", "engineer"],
    },

    # Clean phase
    "types_parsed": {
        "description": "String columns parsed to usable types (dates, numerics)",
        "set_by": "clean",
        "required_for": ["engineer"],
    },
    "missing_handled": {
        "description": "Missing values addressed (imputed, flagged, or dropped)",
        "set_by": "clean",
        "required_for": ["engineer"],
    },
    "outliers_flagged": {
        "description": "Outliers identified and flagged (not necessarily removed)",
        "set_by": "clean",
        "required_for": [],
    },

    # Engineer phase
    "candidate_features_created": {
        "description": "Feature engineering produced candidate columns",
        "set_by": "engineer",
        "required_for": ["cluster", "select"],
    },
    "cheap_prune_done": {
        "description": "Zero-variance and high-missing features removed",
        "set_by": "engineer",
        "required_for": ["cluster"],
    },
    "log_target_created": {
        "description": "Log-transformed target column exists",
        "set_by": "engineer",
        "required_for": [],
    },
    "interaction_terms_created": {
        "description": "Interaction terms created (e.g., feature × category)",
        "set_by": "engineer",
        "required_for": [],
    },

    # Cluster phase
    "clusters_discovered": {
        "description": "Multi-view clustering found meaningful clusters",
        "set_by": "cluster",
        "required_for": [],
    },
    "regime_validated": {
        "description": "At least one feature has different slopes across clusters",
        "set_by": "cluster",
        "required_for": [],
    },
    "cluster_label_added": {
        "description": "cluster_label column added as Track B structural feature",
        "set_by": "cluster",
        "required_for": [],
    },

    # Select phase
    "target_identified": {
        "description": "Target column explicitly identified (by human or LLM)",
        "set_by": "select",
        "required_for": ["report"],
    },
    "features_selected": {
        "description": "Final feature set determined (Track A + Track B)",
        "set_by": "select",
        "required_for": ["report"],
    },
    "structural_features_preserved": {
        "description": "Track B features retained despite low SHAP/MI",
        "set_by": "select",
        "required_for": [],
    },

    # Report phase
    "ols_fitted": {
        "description": "OLS model fitted on log(target)",
        "set_by": "report",
        "required_for": [],
    },
    "tree_fitted": {
        "description": "LightGBM model fitted",
        "set_by": "report",
        "required_for": [],
    },
    "report_generated": {
        "description": "Publication-ready report generated",
        "set_by": "report",
        "required_for": [],
    },

    # Human-set flags
    "target_declared": {
        "description": "Human declared target column in human-notes.md",
        "set_by": "human",
        "required_for": ["cluster"],
    },
    "structural_features_declared": {
        "description": "Human listed structural features in human-notes.md",
        "set_by": "human",
        "required_for": [],
    },
}


# ---------------------------------------------------------------------------
# Flag storage
# ---------------------------------------------------------------------------

def _flags_path(dataset_id: str) -> Path:
    return ARTIFACTS_DIR / dataset_id / "flags.json"


def load_flags(dataset_id: str) -> dict:
    """Load current flags for a dataset.

    Returns: {
        "flags": {flag_name: {"set_at": timestamp, "set_by": phase, "run_id": str, "detail": str}},
        "history": [{"flag": str, "action": "set|unset", "timestamp": str, ...}]
    }
    """
    path = _flags_path(dataset_id)
    if path.exists():
        return json.loads(path.read_text())
    return {"flags": {}, "history": []}


def save_flags(dataset_id: str, data: dict):
    """Save flags to disk."""
    path = _flags_path(dataset_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def set_flag(dataset_id: str, flag_name: str, *,
             run_id: str = "", detail: str = ""):
    """Set a flag for a dataset. Idempotent — re-setting updates timestamp."""
    data = load_flags(dataset_id)
    now = datetime.now(timezone.utc).isoformat()

    catalog_entry = FLAG_CATALOG.get(flag_name, {})
    set_by = catalog_entry.get("set_by", "unknown")

    data["flags"][flag_name] = {
        "set_at": now,
        "set_by": set_by,
        "run_id": run_id,
        "detail": detail,
    }
    data["history"].append({
        "flag": flag_name,
        "action": "set",
        "timestamp": now,
        "run_id": run_id,
        "detail": detail,
    })
    save_flags(dataset_id, data)


def unset_flag(dataset_id: str, flag_name: str, *, reason: str = ""):
    """Remove a flag (e.g., when re-running a phase invalidates prior results)."""
    data = load_flags(dataset_id)
    now = datetime.now(timezone.utc).isoformat()

    if flag_name in data["flags"]:
        del data["flags"][flag_name]
    data["history"].append({
        "flag": flag_name,
        "action": "unset",
        "timestamp": now,
        "reason": reason,
    })
    save_flags(dataset_id, data)


def has_flag(dataset_id: str, flag_name: str) -> bool:
    """Check if a flag is set."""
    data = load_flags(dataset_id)
    return flag_name in data["flags"]


def get_flags(dataset_id: str) -> set[str]:
    """Get all currently set flags."""
    data = load_flags(dataset_id)
    return set(data["flags"].keys())


# ---------------------------------------------------------------------------
# Route checking — can a phase run?
# ---------------------------------------------------------------------------

def check_requirements(dataset_id: str, action: str) -> dict:
    """Check if a phase's required flags are satisfied.

    Returns: {
        "can_proceed": bool,
        "missing": [flag_names],
        "satisfied": [flag_names],
        "optional_missing": [flag_names that aren't required but would enrich],
        "speedrun": bool (True if proceeding without optional flags),
    }
    """
    current = get_flags(dataset_id)

    # Gather required flags for this action
    required = set()
    optional_enriching = set()
    for flag_name, info in FLAG_CATALOG.items():
        if action in info.get("required_for", []):
            required.add(flag_name)

    # Optional enriching: flags from the immediately prior phase
    action_codes = {v: k for k, v in ACTIONS.items()}
    if action in action_codes:
        my_code = action_codes[action]
        for code, act in sorted(ACTIONS.items()):
            if code < my_code:
                # Flags set by prior phases that aren't required
                for flag_name, info in FLAG_CATALOG.items():
                    if info.get("set_by") == act and flag_name not in required:
                        optional_enriching.add(flag_name)

    satisfied = required & current
    missing = required - current
    optional_missing = optional_enriching - current

    return {
        "can_proceed": len(missing) == 0,
        "missing": sorted(missing),
        "satisfied": sorted(satisfied),
        "optional_missing": sorted(optional_missing),
        "speedrun": len(missing) == 0 and len(optional_missing) > 0,
    }


def route_status(dataset_id: str) -> dict:
    """Full route status — what's unlocked, what's blocked, what's completed.

    Returns a dict with per-phase status, like a VN route map.
    """
    current = get_flags(dataset_id)
    status = {}

    for code, action in sorted(ACTIONS.items()):
        req_check = check_requirements(dataset_id, action)

        # Check if this phase has been completed (has flags it sets)
        phase_flags = {f for f, info in FLAG_CATALOG.items() if info.get("set_by") == action}
        completed_flags = phase_flags & current

        if completed_flags:
            phase_status = "completed"
        elif req_check["can_proceed"]:
            phase_status = "unlocked"
        else:
            phase_status = "locked"

        status[f"{code}-{action}"] = {
            "status": phase_status,
            "flags_set": sorted(completed_flags),
            "flags_possible": sorted(phase_flags),
            "missing_requirements": req_check["missing"],
            "speedrun": req_check["speedrun"],
        }

    return status


def print_route_map(dataset_id: str):
    """Print a visual route map to stdout."""
    status = route_status(dataset_id)
    current = get_flags(dataset_id)

    print(f"\n{'='*60}")
    print(f"  Route Map: {dataset_id}")
    print(f"  Flags: {len(current)}/{len(FLAG_CATALOG)}")
    print(f"{'='*60}")

    icons = {"completed": "##", "unlocked": ">>", "locked": "XX"}

    for phase, info in status.items():
        icon = icons.get(info["status"], "??")
        flags_str = ""
        if info["flags_set"]:
            flags_str = f" [{', '.join(info['flags_set'])}]"
        elif info["missing_requirements"]:
            flags_str = f" (needs: {', '.join(info['missing_requirements'])})"

        print(f"  {icon} {phase}: {info['status']}{flags_str}")

    print()
