#!/usr/bin/env python3
"""
Scheduled cleanup cron — runs periodically to keep artifacts/ and data/ tidy.

What it does (automatically, no prompts):
  1. Collects rejected datasets (failed vet, no pipeline investment).
  2. Collects orphan data/ files (no DB record).
  3. Archives graduated datasets (compresses artifacts/, deletes data/).
  4. Prints a summary of what was cleaned and how much space was freed.

What it does NOT do automatically:
  - Touch datasets with max_action_code >= '10' unless they are rejected
    or fully graduated. Mid-pipeline work requires human review.
  - Delete stale datasets. Stale is reported only.

Intended schedule: daily or weekly via cron/system scheduler.

Usage (manual):
    python -m cron.cleanup              # live run
    python -m cron.cleanup --dry-run    # preview only
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.db import init_db
from lib.cleanup import audit, collect_rejected, collect_orphan_data, archive_graduated


def run(dry_run: bool = False) -> dict:
    """Execute all automatic cleanup policies. Returns summary dict."""
    conn = init_db()
    started = datetime.now(timezone.utc).isoformat()
    summary = {
        "started_at": started,
        "dry_run": dry_run,
        "rejected_mb": 0.0,
        "orphan_data_mb": 0.0,
        "archived_mb": 0.0,
        "actions": [],
    }

    # 1. Collect rejected
    actions = collect_rejected(conn, dry_run=dry_run)
    for a in actions:
        summary["rejected_mb"] += a["size_mb"]
        summary["actions"].append(a)

    # 2. Collect orphan data
    actions = collect_orphan_data(conn, dry_run=dry_run)
    for a in actions:
        summary["orphan_data_mb"] += a["size_mb"]
        summary["actions"].append(a)

    # 3. Archive graduated (no-op until graduation is implemented)
    actions = archive_graduated(conn, dry_run=dry_run)
    for a in actions:
        summary["archived_mb"] += a["size_mb"]
        summary["actions"].append(a)

    conn.close()

    total = summary["rejected_mb"] + summary["orphan_data_mb"] + summary["archived_mb"]
    tag = "[dry-run] " if dry_run else ""
    print(f"{tag}cleanup complete — {len(summary['actions'])} actions, {total:.1f} MB {'would be ' if dry_run else ''}freed")
    if summary["rejected_mb"]:
        print(f"  {tag}rejected:      {summary['rejected_mb']:.1f} MB")
    if summary["orphan_data_mb"]:
        print(f"  {tag}orphan data:   {summary['orphan_data_mb']:.1f} MB")
    if summary["archived_mb"]:
        print(f"  {tag}archived:      {summary['archived_mb']:.1f} MB")

    return summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scheduled artifact cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
