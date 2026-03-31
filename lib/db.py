"""Minimal SQLite database helpers. Loads SQL from sql/ folder."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
DB_PATH = Path(__file__).resolve().parent.parent / "observatory.db"


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a connection with row_factory set."""
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def make_run_id() -> str:
    """Chronologically sortable run ID, 10 chars: MMDD-HHMMSS.

    Second-resolution UTC timestamp. Unique for any practical
    single-machine usage; year lives in the DB row.
    """
    now = datetime.now(timezone.utc)
    return f"{now:%m%d-%H%M%S}"


def init_db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    """Create tables and indexes from sql/ files."""
    if conn is None:
        conn = get_conn()
    schema = (SQL_DIR / "schema.sql").read_text()
    indexes = (SQL_DIR / "indexes.sql").read_text()
    conn.executescript(schema)
    conn.executescript(indexes)
    return conn
