"""Minimal SQLite database helpers. Loads SQL from sql/ folder."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
DB_PATH = Path(__file__).resolve().parent.parent / "observatory.db"


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a connection with row_factory set."""
    conn = sqlite3.connect(str(db_path or DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def make_run_id() -> str:
    """Chronologically sortable run ID, 10 chars: MMDD-HHMMSS.

    Second-resolution UTC timestamp. Unique for any practical
    single-machine usage; year lives in the DB row.
    """
    now = datetime.now(timezone.utc)
    return f"{now:%m%d-%H%M%S}"


def init_db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    """Create tables and indexes from sql/ files. Safe to re-run (CREATE IF NOT EXISTS)."""
    if conn is None:
        conn = get_conn()
    schema = (SQL_DIR / "schema.sql").read_text()
    indexes = (SQL_DIR / "indexes.sql").read_text()
    conn.executescript(schema)
    conn.executescript(indexes)
    # Migrate: add columns that may not exist in older DBs
    _migrate(conn)
    return conn


class RunContext:
    """Lifecycle manager for a single pipeline run.

    Encapsulates connection, run_id, and start timestamp. Agents use
    ctx.conn for all mid-run DB queries, then call ctx.finish() to
    write the run record and ctx.close() when fully done.

    Usage:
        ctx = RunContext(dataset_id, ACTION, ACTION_CODE, "analyst")
        ds = ctx.conn.execute("SELECT * FROM datasets WHERE id=?", (dataset_id,)).fetchone()
        # ... do work ...
        ctx.finish(verdict="promote", verdict_reason="...", llm_response=json.dumps(resp))
        ctx.conn.execute("UPDATE datasets SET max_action_code=? WHERE id=?", ...)
        ctx.conn.commit()
        ctx.close()

    finish() inserts the run record but does NOT close the connection,
    because agents often do further DB writes (e.g. update max_action_code)
    after recording the run verdict.
    """

    def __init__(self, dataset_id: str, action: str, action_code: str, agent: str):
        self.dataset_id = dataset_id
        self.action = action
        self.action_code = action_code
        self.agent = agent
        self.conn = get_conn()
        self.run_id = make_run_id()
        self.started_at = datetime.now(timezone.utc).isoformat()

    def finish(
        self,
        *,
        verdict: str,
        verdict_reason: str,
        llm_response: str | None = None,
        artifact_paths: list[str] | None = None,
        prompt_template: str | None = None,
        metrics: str | None = None,
        cost_estimate_usd: float | None = None,
    ) -> None:
        """Insert the completed run record and commit. Does NOT close the connection."""
        import json as _json
        self.conn.execute(
            """INSERT INTO runs
               (id, dataset_id, action, action_code, agent, status,
                started_at, finished_at,
                prompt_template, llm_response, verdict, verdict_reason,
                artifact_paths, metrics, cost_estimate_usd)
               VALUES (?, ?, ?, ?, ?, 'done', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self.run_id, self.dataset_id, self.action, self.action_code, self.agent,
                self.started_at, datetime.now(timezone.utc).isoformat(),
                prompt_template, llm_response, verdict, verdict_reason,
                _json.dumps(artifact_paths or []), metrics, cost_estimate_usd,
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        """Close the DB connection."""
        self.conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive schema migrations to an existing DB."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(datasets)")}
    if "pipeline_type" not in existing:
        conn.execute("ALTER TABLE datasets ADD COLUMN pipeline_type TEXT DEFAULT 'transactional'")
        conn.commit()

    # Migrate candidates → scan_catalog (executescript already created scan_catalog)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "candidates" in tables:
        conn.execute("INSERT OR IGNORE INTO scan_catalog SELECT * FROM candidates")
        conn.execute("DROP TABLE IF EXISTS candidates")
        conn.commit()
