#!/usr/bin/env python3
"""Initialize a fresh observatory.db with schema + seed data.

Run once after cloning:
    python scripts/init_db.py

Safe to re-run — uses INSERT OR IGNORE for seed rows.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.db import init_db


def main():
    conn = init_db()

    # Seed portals
    conn.execute(
        "INSERT OR IGNORE INTO portals (id, url, name, api_type) VALUES (?, ?, ?, ?)",
        ("data-gov-sg", "https://data.gov.sg", "Data.gov.sg", "ckan"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO portals (id, url, name, api_type) VALUES (?, ?, ?, ?)",
        ("local-upload", "local://upload", "Local Upload", "local"),
    )
    conn.commit()
    conn.close()

    print("observatory.db initialized.")
    print("  Tables: portals, datasets, runs, proposed_joins, synthetic_tables, schema_embeddings")
    print("  Portals seeded: data-gov-sg, local-upload")


if __name__ == "__main__":
    main()
