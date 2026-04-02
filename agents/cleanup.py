#!/usr/bin/env python3
"""
Garbage-collect artifacts and data for datasets that won't graduate to cron.

Usage:
    python -m agents.cleanup --audit
    python -m agents.cleanup --collect-rejected --dry-run
    python -m agents.cleanup --collect-rejected --execute
    python -m agents.cleanup --collect-orphan-data --dry-run
    python -m agents.cleanup --all --dry-run
    python -m agents.cleanup --all --execute
    python -m agents.cleanup --stale
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.db import init_db
from lib.cleanup import audit, collect_rejected, collect_orphan_data, archive_graduated


def cmd_audit(conn):
    result = audit(conn)
    print(f"\n=== Disk Usage ===")
    print(f"  artifacts/   {result['artifacts_mb']:.1f} MB")
    print(f"  data/        {result['data_mb']:.1f} MB")

    print(f"\n=== Rejected (safe to delete) ===")
    if result["rejected"]:
        total = sum(r["artifacts_mb"] + r["data_mb"] for r in result["rejected"])
        for r in result["rejected"]:
            mb = r["artifacts_mb"] + r["data_mb"]
            print(f"  {r['id']}  {r['title'][:50]:<50}  {mb:.1f} MB")
        print(f"  Total reclaimable: {total:.1f} MB across {len(result['rejected'])} datasets")
    else:
        print("  (none)")

    print(f"\n=== Orphan data files (no DB record) ===")
    if result["orphan_data"]:
        total = sum(r["size_mb"] for r in result["orphan_data"])
        for r in result["orphan_data"]:
            print(f"  {r['id']}  {r['size_mb']:.1f} MB  {r['path']}")
        print(f"  Total: {total:.1f} MB")
    else:
        print("  (none)")

    if result["stale_30d"]:
        print(f"\n=== Stale (>30 days, mid-pipeline — report only) ===")
        for r in result["stale_30d"]:
            print(f"  {r['id']}  phase={r['max_action_code']}  last_run={r['last_run'] or 'never'}")

    print()


def cmd_collect_rejected(conn, dry_run: bool):
    _prefix = "[dry-run] " if dry_run else ""
    actions = collect_rejected(conn, dry_run=dry_run)
    if not actions:
        print("Nothing to collect (no rejected datasets at vet stage).")
        return
    total_mb = 0.0
    for a in actions:
        status = "would delete" if dry_run else ("deleted" if a["done"] else "FAILED")
        print(f"  {_prefix}{status}  {a['action']:<20}  {a['size_mb']:5.1f} MB  {Path(a['path']).name}")
        total_mb += a["size_mb"]
    print(f"\n  {'Would reclaim' if dry_run else 'Reclaimed'}: {total_mb:.1f} MB")


def cmd_collect_orphan_data(conn, dry_run: bool):
    _prefix = "[dry-run] " if dry_run else ""
    actions = collect_orphan_data(conn, dry_run=dry_run)
    if not actions:
        print("No orphan data files found.")
        return
    total_mb = 0.0
    for a in actions:
        status = "would delete" if dry_run else ("deleted" if a["done"] else "FAILED")
        print(f"  {_prefix}{status}  {a['size_mb']:5.1f} MB  {a['path']}")
        total_mb += a["size_mb"]
    print(f"\n  {'Would reclaim' if dry_run else 'Reclaimed'}: {total_mb:.1f} MB")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="q3d artifact garbage collector")
    parser.add_argument("--audit", action="store_true", help="Show disk usage and candidates")
    parser.add_argument("--collect-rejected", action="store_true", help="Clean rejected datasets")
    parser.add_argument("--collect-orphan-data", action="store_true", help="Clean orphan data/ files")
    parser.add_argument("--archive-graduated", action="store_true", help="Archive graduated datasets (no-op until graduation implemented)")
    parser.add_argument("--all", action="store_true", help="Run all safe policies (rejected + orphan-data)")
    parser.add_argument("--stale", action="store_true", help="Report stale mid-pipeline datasets (no deletion)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Show what would be done (default)")
    parser.add_argument("--execute", action="store_true", help="Actually perform deletions (disables dry-run)")
    args = parser.parse_args()

    dry_run = not args.execute

    conn = init_db()

    if args.audit or not any([args.collect_rejected, args.collect_orphan_data,
                               args.archive_graduated, args.all, args.stale]):
        cmd_audit(conn)
        conn.close()
        return

    if dry_run:
        print("[dry-run mode — pass --execute to actually delete]\n")

    if args.stale:
        result = audit(conn)
        stale = result["stale_30d"]
        if stale:
            print(f"=== Stale datasets (>30 days, stuck mid-pipeline) ===")
            for r in stale:
                print(f"  {r['id']}  phase={r['max_action_code']}  last_run={r['last_run'] or 'never'}  {r['title'][:50]}")
        else:
            print("No stale datasets.")

    if args.collect_rejected or args.all:
        print("=== Collecting rejected datasets ===")
        cmd_collect_rejected(conn, dry_run=dry_run)

    if args.collect_orphan_data or args.all:
        print("\n=== Collecting orphan data files ===")
        cmd_collect_orphan_data(conn, dry_run=dry_run)

    if args.archive_graduated:
        print("\n=== Archiving graduated datasets ===")
        actions = archive_graduated(conn, dry_run=dry_run)
        if not actions:
            print("  No graduated datasets (graduation not yet implemented).")

    conn.close()


if __name__ == "__main__":
    main()
