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
    """Chronologically sortable run ID: MMDD-HHMMSS (UTC)."""
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
    because agents often do further DB writes after recording the verdict.
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
    ) -> None:
        """Insert the completed run record and commit. Does NOT close the connection."""
        import json as _json
        self.conn.execute(
            """INSERT INTO runs
               (id, dataset_id, action, action_code, agent, status,
                started_at, finished_at,
                prompt_template, llm_response, verdict, verdict_reason,
                artifact_paths)
               VALUES (?, ?, ?, ?, ?, 'done', ?, ?, ?, ?, ?, ?, ?)""",
            (
                self.run_id, self.dataset_id, self.action, self.action_code, self.agent,
                self.started_at, datetime.now(timezone.utc).isoformat(),
                prompt_template, llm_response, verdict, verdict_reason,
                _json.dumps(artifact_paths or []),
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        """Close the DB connection."""
        self.conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply schema migrations to an existing DB.

    M1: add pipeline_type to datasets (legacy, kept for existing DBs pre-M2).
    M2: clean runs (drop unused columns), clean datasets (replace pipeline_type
        with dataset_archetype + research_mode, rename rejected_at_action).
    """
    runs_cols    = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    datasets_cols = {row[1] for row in conn.execute("PRAGMA table_info(datasets)")}

    # M2: recreate runs without the bloat columns
    if "entity_type" in runs_cols or "metrics" in runs_cols:
        conn.executescript("""
            ALTER TABLE runs RENAME TO _runs_m2_old;

            CREATE TABLE runs (
                id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                action TEXT NOT NULL,
                action_code TEXT NOT NULL,
                agent TEXT,
                status TEXT DEFAULT 'running',
                started_at TEXT DEFAULT (datetime('now')),
                finished_at TEXT,
                prompt_template TEXT,
                llm_response TEXT,
                verdict TEXT,
                verdict_reason TEXT,
                artifact_paths TEXT
            );

            INSERT INTO runs
                (id, dataset_id, action, action_code, agent, status,
                 started_at, finished_at, prompt_template, llm_response,
                 verdict, verdict_reason, artifact_paths)
            SELECT
                id, dataset_id, action, action_code, agent, status,
                COALESCE(started_at, datetime('now')), finished_at,
                prompt_template, llm_response,
                verdict, verdict_reason, artifact_paths
            FROM _runs_m2_old;

            DROP TABLE _runs_m2_old;
        """)

    # M2: recreate datasets — replace pipeline_type with dataset_archetype + research_mode,
    #     rename rejected_at_action → rejected_at, drop human_notes
    if "pipeline_type" in datasets_cols and "dataset_archetype" not in datasets_cols:
        conn.executescript("""
            ALTER TABLE datasets RENAME TO _datasets_m2_old;

            CREATE TABLE datasets (
                id TEXT PRIMARY KEY,
                portal_id TEXT NOT NULL REFERENCES portals(id),
                resource_url TEXT,
                title TEXT,
                description TEXT,
                schema_shape TEXT,
                format TEXT,
                row_count INTEGER,
                dataset_archetype TEXT DEFAULT 'unknown',
                research_mode TEXT DEFAULT 'predictive',
                update_frequency TEXT,
                max_action_code TEXT DEFAULT '00',
                cron_actions TEXT DEFAULT '[]',
                rejected INTEGER DEFAULT 0,
                rejected_at TEXT,
                reject_reason TEXT,
                last_run_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            INSERT INTO datasets
                (id, portal_id, resource_url, title, description, schema_shape,
                 format, row_count, dataset_archetype, research_mode,
                 update_frequency, max_action_code, cron_actions,
                 rejected, rejected_at, reject_reason, last_run_at,
                 created_at, updated_at)
            SELECT
                id, portal_id, resource_url, title, description, schema_shape,
                format, row_count,
                CASE pipeline_type
                    WHEN 'transactional' THEN 'transactional'
                    WHEN 'reference'     THEN 'reference'
                    ELSE 'unknown'
                END,
                'predictive',
                update_frequency, max_action_code, cron_actions,
                rejected, rejected_at_action, reject_reason, last_run_at,
                created_at, updated_at
            FROM _datasets_m2_old;

            DROP TABLE _datasets_m2_old;
        """)

    # Legacy M1: candidates → scan_catalog
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "candidates" in tables:
        conn.execute("INSERT OR IGNORE INTO scan_catalog SELECT * FROM candidates")
        conn.execute("DROP TABLE IF EXISTS candidates")
        conn.commit()
