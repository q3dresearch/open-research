"""data.gov.sg discovery scanner.

Crawls the v2 datasets listing API page by page, fetches metadata for each
dataset, and inserts CSV scan_catalog above the size threshold into the
scan_catalog table. No LLM calls.

Progress legend per dataset:
    +   added as pending candidate
    .   already known (in datasets or scan_catalog table)
    s   skipped (wrong format or too small)
    x   metadata fetch error
"""

import time
import httpx
from datetime import datetime, timezone

PORTAL_ID = "data-gov-sg"
LIST_URL = "https://api-production.data.gov.sg/v2/public/api/datasets"
META_URL = "https://api-production.data.gov.sg/v2/public/api/datasets/{}/metadata"

REQUEST_DELAY = 0.6  # seconds between API calls


def _fetch_page(page: int) -> list[str]:
    """Return list of dataset IDs on this page. Empty = end of catalog."""
    resp = httpx.get(LIST_URL, params={"page": page, "pageSize": 10}, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    datasets = (body.get("data") or {}).get("datasets") or []
    return [d["datasetId"] for d in datasets if d.get("datasetId")]


def _fetch_meta(dataset_id: str) -> dict | None:
    """Return {name, description, format, size_bytes, column_count} or None on error."""
    try:
        resp = httpx.get(META_URL.format(dataset_id), timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        col_meta = data.get("columnMetadata") or {}
        col_count = len(col_meta.get("order") or [])
        return {
            "name": data.get("name") or dataset_id,
            "description": (data.get("description") or "")[:500],
            "format": (data.get("format") or "").upper(),
            "size_bytes": data.get("datasetSize"),
            "column_count": col_count,
        }
    except Exception as e:
        print(f"\n    [warn] meta error {dataset_id}: {e}")
        return None


def _already_known(conn, dataset_id: str) -> bool:
    in_ds = conn.execute("SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    in_cd = conn.execute("SELECT 1 FROM scan_catalog WHERE id = ?", (dataset_id,)).fetchone()
    return bool(in_ds or in_cd)


def scan(conn, pages: int, dry_run: bool, min_size_bytes: int, page_ceiling: int,
         max_size_bytes: int = 0) -> dict:
    """Scan up to `pages` unscanned pages and insert pending scan_catalog.

    Returns summary dict: {added, skipped, errors}.
    """
    scanned = {
        r[0] for r in conn.execute(
            "SELECT page FROM scan_progress WHERE portal_id = ?", (PORTAL_ID,)
        ).fetchall()
    }

    queue = []
    p = 1
    while len(queue) < pages and p <= page_ceiling:
        if p not in scanned:
            queue.append(p)
        p += 1

    if not queue:
        return {"added": 0, "skipped": 0, "errors": 0, "exhausted": True}

    print(f"  Scanning {len(queue)} pages (next unscanned: page {queue[0]})")
    if dry_run:
        print("  [dry-run: no writes]")

    added = skipped = errors = 0

    for page_num in queue:
        print(f"\n  page {page_num:>4} ", end="", flush=True)

        try:
            ids = _fetch_page(page_num)
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1
            continue

        if not ids:
            print("(end of catalog)")
            if not dry_run:
                conn.execute(
                    "INSERT OR REPLACE INTO scan_progress (portal_id, page, datasets_found) VALUES (?, ?, 0)",
                    (PORTAL_ID, page_num),
                )
                conn.commit()
            break

        page_added = 0
        for ds_id in ids:
            if _already_known(conn, ds_id):
                print(".", end="", flush=True)
                skipped += 1
                continue

            meta = _fetch_meta(ds_id)
            time.sleep(REQUEST_DELAY)

            if meta is None:
                print("x", end="", flush=True)
                errors += 1
                continue

            fmt = meta["format"]
            size = meta["size_bytes"] or 0

            # Skip unprocessable formats, near-empty files, and oversized files
            SKIP_FORMATS = {"PDF", "KMZ", "ZIP", ""}
            if fmt in SKIP_FORMATS:
                reason = f"format={fmt or 'unknown'}"
            elif size < min_size_bytes:
                reason = f"too_small={size}"
            elif max_size_bytes and size > max_size_bytes:
                reason = f"too_large={size}"
            else:
                reason = None

            # GIS formats stored as skipped — queryable for spatial enrichment at join time
            # All CSVs above threshold are pending vet
            status = "pending" if (reason is None and fmt == "CSV") else "skipped"

            if not dry_run:
                conn.execute(
                    """INSERT OR IGNORE INTO scan_catalog
                       (id, portal_id, name, description, format, size_bytes,
                        column_count, status, skip_reason)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ds_id, PORTAL_ID, meta["name"], meta["description"],
                     fmt, size, meta["column_count"], status, reason),
                )

            if status == "pending":
                print("+", end="", flush=True)
                added += 1
                page_added += 1
            else:
                print("s", end="", flush=True)
                skipped += 1

        if not dry_run:
            conn.execute(
                """INSERT OR REPLACE INTO scan_progress
                   (portal_id, page, scanned_at, datasets_found) VALUES (?, ?, ?, ?)""",
                (PORTAL_ID, page_num, datetime.now(timezone.utc).isoformat(), page_added),
            )
            conn.commit()

    return {"added": added, "skipped": skipped, "errors": errors, "exhausted": False}
