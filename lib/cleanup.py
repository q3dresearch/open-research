"""Garbage collection for artifacts and data that will not graduate to cron.

Policies
--------
rejected        Datasets that failed the vet gate (rejected=1 in datasets table).
                Safe to delete: artifacts/{id}/ and data/{id}.csv.
                Rationale: no pipeline investment, no human notes worth keeping.

orphan_data     data/{id}.csv files with no matching record in datasets or
                scan_catalog. Leftover test downloads, etc.

graduated       Future: datasets that have been promoted to cron/. The full
                artifacts/{id}/ tree is compressed to artifacts/{id}.tar.gz
                and the raw data/{id}.csv is deleted. The .tar.gz is kept as
                an audit trail. (No datasets are graduated yet; this path is
                ready for when graduation is implemented.)

stale           Report-only: datasets with no run activity in the last N days
                that are stuck mid-pipeline. Never auto-deleted.

Safety rules
------------
- All destructive actions default to dry_run=True. Pass dry_run=False explicitly.
- observatory.db is the permanent rejection ledger. datasets.rejected,
  datasets.reject_reason, and runs.llm_response are never deleted by cleanup —
  only artifact files and raw data are removed.
- Before deleting any artifact dir, cleanup verifies the DB record is intact
  (rejected=1 AND a vet run exists). If the DB record is missing, cleanup skips
  and warns — DB-first means the reason must be recorded before files are removed.
- Never clean a dataset with max_action_code >= '10' unless it is also rejected
  or graduated (invested pipeline work deserves human review first).
- archive_graduated is a no-op until graduation is implemented.

Why DB instead of tombstone files
----------------------------------
Storing per-dataset memory files (e.g. memory/{id}/00-vet.md) for every rejection
would make the repo as heavy as node_modules at scale (193+ vetted, thousands to
scan). observatory.db already holds datasets.reject_reason + runs.llm_response —
the full structured rejection record. The DB is the durable memory; artifact files
are only needed during active pipeline work.
"""

import shutil
import tarfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

from lib.artifacts import ARTIFACTS_DIR
from lib.ckan import DATA_DIR


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def audit(conn) -> dict:
    """Return disk usage and cleanup candidates per policy.

    Returns
    -------
    {
      "artifacts_mb": float,
      "data_mb": float,
      "rejected": [{"id", "title", "artifacts_mb", "data_mb"}, ...],
      "orphan_data": [{"id", "path", "size_mb"}, ...],
      "graduated": [],         # placeholder
      "stale_30d": [{"id", "title", "max_action_code", "last_run"}, ...],
    }
    """
    result = {
        "artifacts_mb": _dir_size_mb(ARTIFACTS_DIR),
        "data_mb": _dir_size_mb(DATA_DIR),
        "rejected": [],
        "orphan_data": [],
        "graduated": [],
        "stale_30d": [],
    }

    # Rejected datasets
    rows = conn.execute(
        "SELECT id, title FROM datasets WHERE rejected = 1"
    ).fetchall()
    for row in rows:
        did = row["id"]
        result["rejected"].append({
            "id": did,
            "title": row["title"] or did,
            "artifacts_mb": _dir_size_mb(ARTIFACTS_DIR / did),
            "data_mb": _file_size_mb(DATA_DIR / f"{did}.csv"),
        })

    # Orphan data files (in data/ but not in datasets or scan_catalog)
    if DATA_DIR.exists():
        known_ids = {
            r[0] for r in conn.execute("SELECT id FROM datasets").fetchall()
        } | {
            r[0] for r in conn.execute("SELECT id FROM scan_catalog").fetchall()
        }
        for csv in DATA_DIR.glob("*.csv"):
            did = csv.stem
            if did not in known_ids:
                result["orphan_data"].append({
                    "id": did,
                    "path": str(csv),
                    "size_mb": _file_size_mb(csv),
                })

    # Stale: stuck mid-pipeline for >30 days, not rejected
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    stale_rows = conn.execute(
        """
        SELECT d.id, d.title, d.max_action_code,
               MAX(r.finished_at) AS last_run
        FROM datasets d
        LEFT JOIN runs r ON r.dataset_id = d.id
        WHERE d.rejected = 0
          AND d.max_action_code IS NOT NULL
          AND d.max_action_code NOT IN ('50')
        GROUP BY d.id
        HAVING last_run IS NULL OR last_run < ?
        """,
        (cutoff,),
    ).fetchall()
    for row in stale_rows:
        result["stale_30d"].append({
            "id": row["id"],
            "title": row["title"] or row["id"],
            "max_action_code": row["max_action_code"],
            "last_run": row["last_run"],
        })

    return result


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

def collect_rejected(conn, dry_run: bool = True) -> list[dict]:
    """Delete artifacts and cached data for rejected datasets.

    Only removes datasets where:
    - rejected=1 in datasets table (vet failed)
    - max_action_code == '00' (no downstream pipeline work)
    - At least one vet run exists in the runs table (DB record is intact)

    The DB record (datasets.reject_reason + runs.llm_response) is the
    permanent rejection memory. Artifacts are safe to delete once the DB
    confirms the verdict is recorded.

    Returns list of action dicts: {id, action, path, size_mb, done}.
    """
    rows = conn.execute(
        """SELECT d.id, d.title, d.reject_reason,
                  COUNT(r.id) AS run_count
           FROM datasets d
           LEFT JOIN runs r ON r.dataset_id = d.id AND r.action = 'vet'
           WHERE d.rejected = 1
             AND (d.max_action_code = '00' OR d.max_action_code IS NULL)
           GROUP BY d.id"""
    ).fetchall()

    actions = []
    for row in rows:
        did = row["id"]

        # Guard: DB must have a vet run record before we delete artifacts
        if row["run_count"] == 0:
            actions.append({
                "id": did, "action": "skip_no_db_record",
                "path": "", "size_mb": 0.0, "done": False,
                "warning": "No vet run in DB — skipping to avoid data loss",
            })
            continue

        artifact_dir = ARTIFACTS_DIR / did
        data_file = DATA_DIR / f"{did}.csv"

        if artifact_dir.exists():
            size = _dir_size_mb(artifact_dir)
            actions.append(_make_action(did, "delete_artifacts", str(artifact_dir), size))
            if not dry_run:
                shutil.rmtree(artifact_dir)
                actions[-1]["done"] = True

        if data_file.exists():
            size = _file_size_mb(data_file)
            actions.append(_make_action(did, "delete_data", str(data_file), size))
            if not dry_run:
                data_file.unlink()
                actions[-1]["done"] = True

    return actions


def collect_orphan_data(conn, dry_run: bool = True) -> list[dict]:
    """Delete data/ CSV files that have no record in datasets or scan_catalog.

    Returns list of action dicts.
    """
    if not DATA_DIR.exists():
        return []

    known_ids = {
        r[0] for r in conn.execute("SELECT id FROM datasets").fetchall()
    } | {
        r[0] for r in conn.execute("SELECT id FROM scan_catalog").fetchall()
    }

    actions = []
    for csv in sorted(DATA_DIR.glob("*.csv")):
        did = csv.stem
        if did not in known_ids:
            size = _file_size_mb(csv)
            actions.append(_make_action(did, "delete_orphan_data", str(csv), size))
            if not dry_run:
                csv.unlink()
                actions[-1]["done"] = True

    return actions


def archive_graduated(conn, dry_run: bool = True) -> list[dict]:
    """Compress artifacts for graduated datasets and delete raw data.

    A dataset is graduated when cron_actions is non-empty (set by graduation
    process — not yet implemented). This function is a no-op until that field
    is populated.

    Archive format: artifacts/{id}.tar.gz (replaces artifacts/{id}/ dir).
    """
    # Check if cron_actions column exists yet
    cols = {r[1] for r in conn.execute("PRAGMA table_info(datasets)").fetchall()}
    if "cron_actions" not in cols:
        return []  # graduation not yet implemented

    rows = conn.execute(
        "SELECT id, title FROM datasets WHERE cron_actions IS NOT NULL AND cron_actions NOT IN ('', '[]')"
    ).fetchall()

    actions = []
    for row in rows:
        did = row["id"]
        artifact_dir = ARTIFACTS_DIR / did
        archive_path = ARTIFACTS_DIR / f"{did}.tar.gz"
        data_file = DATA_DIR / f"{did}.csv"

        if artifact_dir.exists() and not archive_path.exists():
            size = _dir_size_mb(artifact_dir)
            actions.append(_make_action(did, "archive_artifacts", str(artifact_dir), size))
            if not dry_run:
                with tarfile.open(archive_path, "w:gz") as tar:
                    tar.add(artifact_dir, arcname=did)
                shutil.rmtree(artifact_dir)
                actions[-1]["done"] = True

        if data_file.exists():
            size = _file_size_mb(data_file)
            actions.append(_make_action(did, "delete_data", str(data_file), size))
            if not dry_run:
                data_file.unlink()
                actions[-1]["done"] = True

    return actions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / 1_048_576, 2)


def _file_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return round(path.stat().st_size / 1_048_576, 2)


def _make_action(dataset_id: str, action: str, path: str, size_mb: float) -> dict:
    return {"id": dataset_id, "action": action, "path": path, "size_mb": size_mb, "done": False}
