# Download Guide

Each data portal has its own download method. This guide documents how q3d fetches
full datasets from each supported source, and what to do when downloads fail.

---

## data.gov.sg

### Authentication

data.gov.sg is public and works without a key, but rate limits are strict (5 req/min).
An API key raises those limits significantly.

Set in `.env`:
```
DATA_GOV_SG_API_KEY=your-key-here
```

Header sent: `x-api-key: YOUR_KEY`

Get a key: https://guide.data.gov.sg/developer-guide/api-overview/how-to-request-an-api-key

---

### Method 1: Bulk Download (preferred for full datasets)

Used by: `lib/ckan.fetch_all_rows_bulk()`

Two-step flow:

**Step 1** — Initiate the export job:
```
GET https://api-open.data.gov.sg/v1/public/api/datasets/{datasetId}/initiate-download
```
Returns immediately with `{"code": 200, "data": {"message": "Download initiated"}}`.

**Step 2** — Poll until ready:
```
GET https://api-open.data.gov.sg/v1/public/api/datasets/{datasetId}/poll-download
```
Returns `{"data": {"status": "QUEUED"|"PROCESSING"|"READY", "url": "https://..."}}`.
When `status == "READY"`, `url` is a pre-signed download link for the full CSV.

**Step 3** — Download the CSV directly from the pre-signed URL.

Progress output:
```
  Initiating bulk download for d_8b84c4ee58e3cfc0ece0d773c8ca6abc...
  Download queued. Polling for ready URL...
  [  12s] status: PROCESSING...
  [  15s] status: READY
  Ready after 15s. Downloading CSV...
  Downloaded 21.6 MB in 4.2s
  Bulk download complete: 286,370 rows × 10 cols in 19s
```

Use when: downloading a complete dataset for full pipeline analysis.

---

### Method 2: Paginated CKAN Search (fallback / samples)

Used by: `lib/ckan.fetch_all_rows()`, `lib/ckan.fetch_rows()`

```
GET https://data.gov.sg/api/action/datastore_search
    ?resource_id={datasetId}&limit=5000&offset={N}
```

Paginates through rows with a 2s delay between pages to respect rate limits.
Slower than bulk download but works for partial fetches and small datasets.

Use when: bulk download is unavailable, or you only need a sample.

**Common errors:**
- `429 Too Many Requests` — rate limit hit, increase `page_delay` or add an API key
- `ReadTimeout` — server slow, retried automatically with exponential backoff

---

### Finding dataset IDs

Dataset ID format: `d_` followed by a hex string, e.g. `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`.

Find it in the URL:
```
https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                              this is the datasetId
```

Or via the metadata API:
```
GET https://api-production.data.gov.sg/v2/public/api/datasets/{datasetId}/metadata
```

---

## Adding a new portal

When adding support for a new data portal, document it here with:

1. **Authentication** — how to configure keys, where to set them in `.env`
2. **Download method** — the API flow, endpoints, response format
3. **Progress logging** — what the terminal output looks like
4. **Common errors** — rate limits, timeouts, format quirks
5. **Finding dataset IDs** — how to locate the right ID for a dataset

Then add the portal to `configs/portals.yaml` and implement a fetcher in `lib/`.
