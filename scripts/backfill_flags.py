#!/usr/bin/env python3
"""Backfill flags.json from existing artifacts for datasets that ran before the flag system.

Inspects artifact filesystem + DB to reconstruct which flags should be set.
Run once per dataset that has prior artifacts.

Usage: python scripts/backfill_flags.py <dataset_id>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.artifacts import ARTIFACTS_DIR, ACTION_CODES, action_dir
from lib.flags import set_flag, load_flags
from lib.db import get_conn


def backfill(dataset_id: str):
    base = ARTIFACTS_DIR / dataset_id
    if not base.exists():
        print(f"No artifacts found for {dataset_id}")
        return

    print(f"Backfilling flags for {dataset_id}")
    existing = load_flags(dataset_id)
    already = set(existing["flags"].keys())

    # --- 00-vet ---
    vet_artifacts = list(base.glob("00-vet-*.md"))
    if vet_artifacts:
        # Check DB for pass verdict
        conn = get_conn()
        row = conn.execute(
            "SELECT verdict, id FROM runs WHERE dataset_id=? AND action='vet' ORDER BY finished_at DESC LIMIT 1",
            (dataset_id,)
        ).fetchone()
        conn.close()
        if row and row["verdict"] == "pass" and "schema_vetted" not in already:
            set_flag(dataset_id, "schema_vetted", run_id=row["id"], detail="backfilled")
            print("  + schema_vetted")

    # --- 10-eda ---
    eda_dir = base / action_dir(ACTION_CODES["eda"], "eda")
    if eda_dir.exists():
        eda_runs = sorted([d for d in eda_dir.iterdir() if d.is_dir()])
        if eda_runs:
            if "eda_profiled" not in already:
                set_flag(dataset_id, "eda_profiled", detail="backfilled")
                print("  + eda_profiled")
            # Check for column_assessment
            for run in eda_runs:
                ca = run / "tables" / "column_assessment.csv"
                if ca.exists() and "column_assessment_exists" not in already:
                    set_flag(dataset_id, "column_assessment_exists", detail="backfilled")
                    print("  + column_assessment_exists")
                    break

    # --- 15-clean ---
    clean_dir = base / action_dir(ACTION_CODES["clean"], "clean")
    if clean_dir.exists():
        cp = clean_dir / "clean_pipeline.py"
        if cp.exists():
            if "types_parsed" not in already:
                set_flag(dataset_id, "types_parsed", detail="backfilled")
                print("  + types_parsed")
            if "missing_handled" not in already:
                set_flag(dataset_id, "missing_handled", detail="backfilled")
                print("  + missing_handled")

    # --- 20-engineer ---
    eng_dir = base / action_dir(ACTION_CODES["engineer"], "engineer")
    if eng_dir.exists():
        pp = eng_dir / "pipeline.py"
        if pp.exists():
            if "candidate_features_created" not in already:
                # Count steps in pipeline
                code = pp.read_text()
                import re
                steps = re.findall(r"^def (step_\w+)\(", code, re.MULTILINE)
                set_flag(dataset_id, "candidate_features_created",
                         detail=f"backfilled, {len(steps)} steps")
                print(f"  + candidate_features_created ({len(steps)} steps)")

            # Check verdict from DB
            conn = get_conn()
            row = conn.execute(
                "SELECT verdict, id FROM runs WHERE dataset_id=? AND action='engineer' ORDER BY finished_at DESC LIMIT 1",
                (dataset_id,)
            ).fetchone()
            conn.close()
            if row and row["verdict"] == "sufficient" and "cheap_prune_done" not in already:
                set_flag(dataset_id, "cheap_prune_done", run_id=row["id"], detail="backfilled")
                print("  + cheap_prune_done")

    # --- 25-cluster ---
    cluster_dir = base / action_dir(ACTION_CODES["cluster"], "cluster")
    if cluster_dir.exists():
        labels = cluster_dir / "cluster_labels.csv"
        if labels.exists() and "cluster_label_added" not in already:
            set_flag(dataset_id, "cluster_label_added", detail="backfilled")
            print("  + cluster_label_added")

    # --- 30-select ---
    select_dir = base / action_dir(ACTION_CODES["select"], "select")
    if select_dir.exists():
        sel_runs = sorted([d for d in select_dir.iterdir() if d.is_dir()])
        if sel_runs:
            report = sel_runs[-1] / "feature_report.json"
            if report.exists():
                data = json.loads(report.read_text())
                target = data.get("target_col")
                if target and "target_identified" not in already:
                    set_flag(dataset_id, "target_identified", detail=f"backfilled: {target}")
                    print(f"  + target_identified ({target})")
                if data.get("llm_review", {}).get("final_keep") and "features_selected" not in already:
                    n = len(data["llm_review"]["final_keep"])
                    set_flag(dataset_id, "features_selected", detail=f"backfilled: {n} features")
                    print(f"  + features_selected ({n} features)")

    # --- Check human-notes for target declaration ---
    hn = base / "human-notes.md"
    if hn.exists():
        import re
        text = hn.read_text()
        m = re.search(r'(?:target|predict|y_col)\s*[:=]\s*(\S+)', text, re.IGNORECASE)
        if m and "target_declared" not in already:
            set_flag(dataset_id, "target_declared", detail=f"backfilled: {m.group(1)}")
            print(f"  + target_declared ({m.group(1)})")
        if "## Structural features" in text and "structural_features_declared" not in already:
            set_flag(dataset_id, "structural_features_declared", detail="backfilled")
            print("  + structural_features_declared")

    print(f"\nDone. Run print_route_map('{dataset_id}') to see current state.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/backfill_flags.py <dataset_id>")
        sys.exit(1)
    backfill(sys.argv[1])
