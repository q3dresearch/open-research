"""Phase duration estimation from historical run records.

Uses started_at / finished_at from the runs table to build empirical
per-action timing profiles and scale them by row count.

Functions
---------
estimate_phase_s(conn, action, row_count)
    Returns estimated seconds for a phase, or None if no history.

format_eta(seconds)
    Formats seconds as a human-readable string ("~2m", "~45s", etc.)

phase_timing_report(conn)
    Returns a dict of {action: {median_s, sample_count, median_rows}}
    suitable for display in a Streamlit GUI or CLI status command.
"""

import statistics
import sqlite3


def estimate_phase_s(conn: sqlite3.Connection, action: str, row_count: int) -> int | None:
    """Estimate how long `action` will take for a dataset with `row_count` rows.

    Approach:
    - Collect all completed runs for this action where both started_at and
      finished_at are recorded.
    - Scale the median historical duration by the ratio of target row_count
      to median historical row_count.
    - Returns None when there is insufficient history (< 2 data points).

    The scaling is linear, which works well for IO-bound phases (download,
    profiling) but underestimates LLM latency which has a fixed component.
    A floor of the 25th-percentile duration is applied to avoid estimates
    of 0s for tiny datasets.
    """
    rows = conn.execute(
        """
        SELECT
            ROUND((julianday(r.finished_at) - julianday(r.started_at)) * 86400) AS duration_s,
            d.row_count
        FROM runs r
        JOIN datasets d ON d.id = r.dataset_id
        WHERE r.action = ?
          AND r.started_at IS NOT NULL
          AND r.finished_at IS NOT NULL
          AND d.row_count > 0
          AND r.status = 'done'
        ORDER BY r.finished_at DESC
        LIMIT 30
        """,
        (action,),
    ).fetchall()

    if len(rows) < 2:
        return None

    durations = [r[0] for r in rows if r[0] and r[0] > 0]
    hist_rows = [r[1] for r in rows if r[0] and r[0] > 0]

    if len(durations) < 2:
        return None

    median_dur = statistics.median(durations)
    median_row = statistics.median(hist_rows)
    floor_dur = sorted(durations)[len(durations) // 4]  # 25th percentile as floor

    if median_row == 0 or row_count == 0:
        return int(max(median_dur, floor_dur))

    scaled = median_dur * (row_count / median_row)
    return int(max(scaled, floor_dur))


def format_eta(seconds: int | None) -> str:
    """Human-readable duration string.

    Examples: "~45s", "~2m", "~1h 15m", "unknown"
    """
    if seconds is None:
        return "unknown"
    if seconds < 60:
        return f"~{int(seconds)}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"~{int(minutes)}m"
    hours = minutes // 60
    mins = minutes % 60
    return f"~{int(hours)}h {int(mins)}m"


def phase_timing_report(conn: sqlite3.Connection) -> dict:
    """Return median duration + sample count per action, for status displays.

    Returns:
        {
          "vet":      {"median_s": 12, "sample_count": 189, "median_rows": 500},
          "eda":      {"median_s": 45, "sample_count": 4,   "median_rows": 52203},
          ...
        }
    """
    rows = conn.execute(
        """
        SELECT
            r.action,
            ROUND((julianday(r.finished_at) - julianday(r.started_at)) * 86400) AS duration_s,
            d.row_count
        FROM runs r
        JOIN datasets d ON d.id = r.dataset_id
        WHERE r.started_at IS NOT NULL
          AND r.finished_at IS NOT NULL
          AND d.row_count > 0
          AND r.status = 'done'
        """
    ).fetchall()

    by_action: dict[str, list] = {}
    for row in rows:
        action = row[0]
        dur = row[1]
        rc = row[2]
        if dur and dur > 0:
            by_action.setdefault(action, []).append((dur, rc))

    result = {}
    for action, pairs in by_action.items():
        durations = [p[0] for p in pairs]
        row_counts = [p[1] for p in pairs]
        result[action] = {
            "median_s": int(statistics.median(durations)),
            "sample_count": len(durations),
            "median_rows": int(statistics.median(row_counts)),
        }
    return result
