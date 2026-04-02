"""Fetch datasets from data.gov.sg APIs.

Download strategies
-------------------
data.gov.sg offers two download paths:

1. Bulk download (preferred for full datasets)
   initiate-download → poll-download → direct CSV URL
   Avoids pagination rate limits. Returns a pre-signed URL for the full file.
   Endpoint: https://api-open.data.gov.sg/v1/public/api/datasets/{id}/initiate-download
             https://api-open.data.gov.sg/v1/public/api/datasets/{id}/poll-download

2. Paginated CKAN search (fallback / small slices)
   Datastore search API with limit/offset pagination.
   Rate-limited to 5 req/min without an API key.
   Endpoint: https://data.gov.sg/api/action/datastore_search

Use fetch_all_rows_bulk() for full datasets. Use fetch_rows() for small samples.
"""

import io
import os
import time
import httpx
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# data.gov.sg endpoints
DATASTORE_URL = "https://data.gov.sg/api/action/datastore_search"
METADATA_URL = "https://api-production.data.gov.sg/v2/public/api/datasets"
COLLECTION_URL = "https://api-production.data.gov.sg/v2/public/api/collections"
INITIATE_URL = "https://api-open.data.gov.sg/v1/public/api/datasets/{}/initiate-download"
POLL_URL = "https://api-open.data.gov.sg/v1/public/api/datasets/{}/poll-download"


def _load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _get_datagov_headers() -> dict:
    """Return auth headers for data.gov.sg API if key is available."""
    _load_env()
    key = os.environ.get("DATA_GOV_SG_API_KEY")
    if key:
        return {"x-api-key": key}
    return {}


def _fetch_metadata_local(dataset_id: str) -> dict:
    """Build a metadata dict from the local DB record for locally-uploaded datasets."""
    import sqlite3
    db_path = Path(__file__).resolve().parent.parent / "observatory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    conn.close()
    title = (row["title"] if row else None) or dataset_id
    desc  = (row["description"] if row else None) or ""
    # Best-effort column list from the CSV header
    csv_path = DATA_DIR / f"{dataset_id}.csv"
    columns = []
    if csv_path.exists():
        import pandas as _pd
        try:
            sample = _pd.read_csv(csv_path, nrows=0)
            columns = [{"name": c, "title": c, "data_type": "Text", "categorical": False}
                       for c in sample.columns]
        except Exception:
            pass
    return {
        "dataset_id": dataset_id,
        "name": title,
        "description": desc,
        "format": "CSV",
        "managed_by": "local",
        "last_updated": None,
        "coverage_start": None,
        "coverage_end": None,
        "dataset_size": None,
        "collection_ids": [],
        "columns": columns,
    }


def fetch_metadata(dataset_id: str) -> dict:
    """Fetch rich metadata: title, description, publisher, column info, etc.

    Local datasets (id starts with 'local_') are served from the DB and CSV header
    without hitting the remote API.
    """
    if dataset_id.startswith("local_"):
        return _fetch_metadata_local(dataset_id)
    resp = httpx.get(f"{METADATA_URL}/{dataset_id}/metadata", timeout=15)
    resp.raise_for_status()
    data = resp.json()["data"]

    # Flatten column metadata into a clean list
    col_meta = data.get("columnMetadata", {})
    meta_map = col_meta.get("metaMapping", {})
    order = col_meta.get("order", [])

    columns = []
    for col_id in order:
        info = meta_map.get(col_id, {})
        columns.append({
            "name": info.get("name"),
            "title": info.get("columnTitle"),
            "data_type": info.get("dataType"),
            "categorical": info.get("isCategorical", False),
        })

    return {
        "dataset_id": data["datasetId"],
        "name": data.get("name"),
        "description": data.get("description"),
        "format": data.get("format"),
        "managed_by": data.get("managedBy"),
        "last_updated": data.get("lastUpdatedAt"),
        "coverage_start": data.get("coverageStart"),
        "coverage_end": data.get("coverageEnd"),
        "dataset_size": data.get("datasetSize"),
        "collection_ids": data.get("collectionIds", []),
        "columns": columns,
    }


def fetch_collection(collection_id: str) -> dict | None:
    """Fetch collection metadata: name, description, frequency, child datasets.

    Returns None if the collection endpoint returns no usable data.
    """
    resp = httpx.get(f"{COLLECTION_URL}/{collection_id}/metadata", timeout=15)
    resp.raise_for_status()
    meta = (resp.json().get("data") or {}).get("collectionMetadata") or {}
    if not meta.get("collectionId"):
        return None
    return {
        "collection_id": meta["collectionId"],
        "name": meta.get("name"),
        "description": meta.get("description"),
        "frequency": meta.get("frequency"),
        "sources": meta.get("sources", []),
        "managed_by": meta.get("managedBy"),
        "child_datasets": meta.get("childDatasets", []),
    }


def fetch_rows(dataset_id: str, limit: int = 5000) -> dict:
    """Fetch rows from the datastore search API.

    Returns dict with 'fields', 'records', 'total'.
    """
    headers = _get_datagov_headers()
    for attempt in range(3):
        resp = httpx.get(
            DATASTORE_URL,
            params={"resource_id": dataset_id, "limit": limit},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 429:
            wait = 2 ** attempt
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"API error: {data}")
        return data["result"]
    resp.raise_for_status()  # raise on final failure


def fetch_to_dataframe(dataset_id: str, limit: int = 5000) -> pd.DataFrame:
    """Fetch a dataset and return as a pandas DataFrame."""
    result = fetch_rows(dataset_id, limit=limit)
    df = pd.DataFrame(result["records"])
    if "_id" in df.columns:
        df = df.drop(columns=["_id"])
    return df


def fetch_all_rows(dataset_id: str, page_size: int = 5000,
                    page_delay: float = 2.0) -> pd.DataFrame:
    """Paginate through the entire dataset. Returns full DataFrame.

    Uses conservative pacing to avoid data.gov.sg rate limits:
    - page_delay seconds between successful requests
    - Exponential backoff on 429s (up to 60s, 8 retries)
    """
    frames = []
    offset = 0
    total = None

    headers = _get_datagov_headers()
    while True:
        for attempt in range(8):
            try:
                resp = httpx.get(
                    DATASTORE_URL,
                    params={"resource_id": dataset_id, "limit": page_size, "offset": offset},
                    headers=headers,
                    timeout=60,
                )
                if resp.status_code == 429:
                    wait = min(2 ** (attempt + 1), 60)
                    print(f"  Rate limited at offset {offset}, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if not data.get("success"):
                    raise RuntimeError(f"API error: {data}")
                break
            except httpx.ReadTimeout:
                wait = min(2 ** (attempt + 1), 60)
                print(f"  Timeout at offset {offset}, retrying in {wait}s...")
                time.sleep(wait)
        else:
            raise RuntimeError(f"Failed after 8 attempts at offset {offset}")

        result = data["result"]
        records = result["records"]
        if total is None:
            total = result.get("total", 0)
            print(f"  Total rows: {total}")

        if not records:
            break

        frames.append(pd.DataFrame(records))
        offset += len(records)
        print(f"  Fetched {offset}/{total} rows...")

        if offset >= total:
            break

        # Pace requests to stay under rate limits
        time.sleep(page_delay)

    df = pd.concat(frames, ignore_index=True)
    if "_id" in df.columns:
        df = df.drop(columns=["_id"])
    return df


def fetch_all_rows_bulk(dataset_id: str, poll_interval: float = 3.0,
                        timeout: float = 300.0) -> pd.DataFrame:
    """Download a full dataset via the initiate-download + poll-download flow.

    This is the preferred method for full datasets. It requests a pre-signed
    CSV download URL from data.gov.sg rather than paginating row by row.

    Steps:
      1. POST /initiate-download  → server queues the export job
      2. GET  /poll-download      → poll until status == "READY", then download URL
      3. Download the CSV directly

    Args:
        dataset_id:    data.gov.sg dataset ID (e.g. d_8b84c4ee58e3cfc0ece0d773c8ca6abc)
        poll_interval: seconds between status polls (default 3s)
        timeout:       give up after this many seconds (default 300s = 5 min)

    Returns:
        Full DataFrame with all rows.
    """
    headers = _get_datagov_headers()
    t0 = time.time()

    # 1. Initiate download
    print(f"  Initiating bulk download for {dataset_id}...")
    resp = httpx.get(INITIATE_URL.format(dataset_id), headers=headers, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") not in (200, 201) and "errorMsg" in result:
        raise RuntimeError(f"Initiate download failed: {result['errorMsg']}")
    print(f"  Download queued. Polling for ready URL...")

    # 2. Poll until READY
    download_url = None
    attempt = 0
    while True:
        elapsed = time.time() - t0
        if elapsed > timeout:
            raise RuntimeError(f"Bulk download timed out after {elapsed:.0f}s")

        resp = httpx.get(POLL_URL.format(dataset_id), headers=headers, timeout=30)
        resp.raise_for_status()
        poll = resp.json()
        status = poll.get("data", {}).get("status", "UNKNOWN")

        print(f"  [{elapsed:5.0f}s] status: {status}...", end="\r", flush=True)

        if status == "READY":
            download_url = poll["data"]["url"]
            print(f"\n  Ready after {elapsed:.0f}s. Downloading CSV...")
            break

        attempt += 1
        time.sleep(poll_interval)

    # 3. Download the CSV
    t_dl = time.time()
    resp = httpx.get(download_url, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    elapsed_dl = time.time() - t_dl
    size_mb = len(resp.content) / 1_048_576
    print(f"  Downloaded {size_mb:.1f} MB in {elapsed_dl:.1f}s")

    df = pd.read_csv(io.BytesIO(resp.content))
    if "_id" in df.columns:
        df = df.drop(columns=["_id"])

    total_elapsed = time.time() - t0
    print(f"  Bulk download complete: {len(df):,} rows × {len(df.columns)} cols in {total_elapsed:.0f}s")
    return df


def save_dataset(dataset_id: str, df: pd.DataFrame) -> Path:
    """Save a DataFrame to data/{dataset_id}.csv. Returns the file path."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{dataset_id}.csv"
    df.to_csv(path, index=False)
    return path
