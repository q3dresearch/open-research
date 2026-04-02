#!/usr/bin/env python3
"""
Discovery agent: crawls configured portals and populates the scan_catalog table.

Reads portal config from configs/portals.yaml. Dispatches to the right
scanner in lib/discover/ based on portal api_type. No LLM calls.

Re-runs are incremental — scan_progress tracks which pages are done so
each invocation picks up where the last left off.

Usage:
    python -m agents.discover                        # scan next 20 pages (all portals)
    python -m agents.discover --portal data-gov-sg   # one portal only
    python -m agents.discover --pages 50             # scan more pages
    python -m agents.discover --status               # show scan progress
    python -m agents.discover --reset                # clear progress (full re-scan)
    python -m agents.discover --dry-run              # scan without writing to DB
"""

import argparse
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.db import init_db

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "portals.yaml"

SCANNERS = {
    "ckan": "lib.discover.datagov_sg",  # data.gov.sg uses CKAN-compatible API
}


def _load_portals(portal_filter: str | None) -> list[dict]:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    portals = config.get("portals", [])
    if portal_filter:
        portals = [p for p in portals if p["id"] == portal_filter]
    return portals


def _get_scanner(api_type: str):
    module_path = SCANNERS.get(api_type)
    if not module_path:
        raise ValueError(f"No scanner registered for api_type={api_type!r}")
    import importlib
    return importlib.import_module(module_path)


def cmd_scan(pages: int, portal_filter: str | None, dry_run: bool):
    conn = init_db()
    portals = _load_portals(portal_filter)

    if not portals:
        print(f"No portals found (filter={portal_filter!r}). Check configs/portals.yaml.")
        conn.close()
        return

    total_added = total_skipped = total_errors = 0

    for portal in portals:
        portal_id = portal["id"]
        api_type = portal.get("api_type", "ckan")
        scanner_cfg = portal.get("scanner", {})
        min_size = scanner_cfg.get("min_size_bytes", 100_000)
        max_size = scanner_cfg.get("max_size_bytes", 0)   # 0 = no upper limit
        page_ceiling = scanner_cfg.get("page_ceiling", 600)

        print(f"\n[{portal_id}]  api_type={api_type}")

        # Ensure portal row exists
        conn.execute(
            "INSERT OR IGNORE INTO portals (id, url, name, api_type) VALUES (?, ?, ?, ?)",
            (portal_id, portal.get("url", ""), portal.get("name", portal_id), api_type),
        )
        conn.commit()

        try:
            scanner = _get_scanner(api_type)
        except ValueError as e:
            print(f"  Skipping: {e}")
            continue

        result = scanner.scan(
            conn=conn,
            pages=pages,
            dry_run=dry_run,
            min_size_bytes=min_size,
            max_size_bytes=max_size,
            page_ceiling=page_ceiling,
        )

        if result.get("exhausted"):
            print(f"\n  All pages already scanned. Use --reset to re-scan.")
        else:
            total_added += result["added"]
            total_skipped += result["skipped"]
            total_errors += result["errors"]

    pending = conn.execute("SELECT COUNT(*) FROM scan_catalog WHERE status='pending'").fetchone()[0]
    print(f"\n{'='*40}")
    print(f"Added    : {total_added}")
    print(f"Skipped  : {total_skipped}  (wrong format or too small)")
    print(f"Errors   : {total_errors}")
    print(f"Pending vet in DB: {pending}")
    conn.close()


def cmd_status(portal_filter: str | None):
    conn = init_db()
    portals = _load_portals(portal_filter)

    for portal in portals:
        pid = portal["id"]
        pages_done = conn.execute(
            "SELECT COUNT(*) FROM scan_progress WHERE portal_id = ?", (pid,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM scan_catalog WHERE portal_id = ? GROUP BY status", (pid,)
        ).fetchall()
        print(f"\n[{pid}]")
        print(f"  Pages scanned : {pages_done} / ~{portal.get('scanner', {}).get('page_ceiling', 600)}")
        for row in rows:
            print(f"  {row[0]:<12}: {row[1]}")

    conn.close()


def cmd_reset(portal_filter: str | None):
    conn = init_db()
    portals = _load_portals(portal_filter)
    for portal in portals:
        pid = portal["id"]
        n = conn.execute(
            "SELECT COUNT(*) FROM scan_progress WHERE portal_id = ?", (pid,)
        ).fetchone()[0]
        conn.execute("DELETE FROM scan_progress WHERE portal_id = ?", (pid,))
        print(f"[{pid}] Cleared {n} scan_progress rows.")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crawl configured portals and populate the scan_catalog table (no LLM)."
    )
    parser.add_argument("--pages", type=int, default=20,
                        help="Unscanned pages to process per portal (default 20)")
    parser.add_argument("--portal", type=str, default=None,
                        help="Limit to one portal ID (default: all portals)")
    parser.add_argument("--reset", action="store_true",
                        help="Clear scan progress so next run re-scans from page 1")
    parser.add_argument("--status", action="store_true",
                        help="Print scan progress summary and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and filter but do not write to DB")
    args = parser.parse_args()

    if args.reset:
        cmd_reset(args.portal)
    elif args.status:
        cmd_status(args.portal)
    else:
        cmd_scan(args.pages, args.portal, dry_run=args.dry_run)
