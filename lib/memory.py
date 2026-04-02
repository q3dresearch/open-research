"""Research memory system — per-dataset phase journals and artifact index.

Phase journals capture the model's chain-of-thought across all runs so that
future runs (and future datasets) can reference what was tried and learned.

Structure:
  memory/
    main/
      SOUL.md        ← research identity (always loaded into agent context)
      AGENTS.md      ← operational rules
      TOOLS.md       ← arsenal reference docs
    {dataset_id}/
      00-vet.md      ← journal of all vet runs
      10-eda.md
      15-clean.md
      20-engineer.md
      25-cluster.md
      30-select.md
      50-report.md
      index.json     ← artifact map: columns, tables, charts, concerns

Design principles:
- Phase journals are append-only markdown. Each run opens a header, then each
  LLM reasoning step is appended immediately after the call.
- index.json is the agent's mental map — it knows what artifacts exist and their
  one-line summaries without loading the full data.
- Agents never read full artifact files into context. They read the index and
  call tools to get cheap slices (head, describe, stat result).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT / "memory"


# ── internal helpers ─────────────────────────────────────────────────────────

def _phase_path(dataset_id: str, phase_code: str, phase_name: str) -> Path:
    d = MEMORY_DIR / dataset_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{phase_code}-{phase_name}.md"


def _index_path(dataset_id: str) -> Path:
    d = MEMORY_DIR / dataset_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "index.json"


# ── phase journal ─────────────────────────────────────────────────────────────

def open_run(dataset_id: str, phase_code: str, phase_name: str, run_id: str) -> None:
    """Open a new run section in the phase journal."""
    path = _phase_path(dataset_id, phase_code, phase_name)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with path.open("a") as f:
        f.write(f"\n## Run {run_id}  _{ts}_\n\n")


def log_step(
    dataset_id: str,
    phase_code: str,
    phase_name: str,
    step_name: str,
    reasoning: str,
    result: str,
) -> None:
    """Append one step's reasoning + outcome to the phase journal.

    reasoning: the model's text before the JSON block — its actual thinking.
    result:    a one-line summary of what happened (e.g. "OK: +1 col (foo)").
    """
    path = _phase_path(dataset_id, phase_code, phase_name)
    reasoning = (reasoning or "").strip()
    if len(reasoning) > 2000:
        reasoning = reasoning[:1800] + "\n\n*... [truncated]*"
    with path.open("a") as f:
        f.write(f"### {step_name}\n{reasoning}\n\n**→** {result}\n\n")


def read_phase_log(dataset_id: str, phase_code: str, phase_name: str) -> str:
    """Read the full phase journal for a dataset."""
    path = _phase_path(dataset_id, phase_code, phase_name)
    return path.read_text() if path.exists() else ""


def read_upstream_logs(dataset_id: str, before_code: str) -> str:
    """Return combined journals for all phases that ran before before_code."""
    from lib.artifacts import ACTIONS
    parts = []
    for code, name in sorted(ACTIONS.items()):
        if code >= before_code:
            break
        log = read_phase_log(dataset_id, code, name)
        if log.strip():
            parts.append(f"# {code}-{name}\n{log.strip()}")
    return "\n\n---\n\n".join(parts)


# ── artifact index ────────────────────────────────────────────────────────────

def read_index(dataset_id: str) -> dict:
    """Load the artifact index for a dataset. Returns empty scaffold if not yet created."""
    path = _index_path(dataset_id)
    if path.exists():
        return json.loads(path.read_text())
    return {"columns": {}, "tables": {}, "charts": {}, "concerns": []}


def update_index(dataset_id: str, patch: dict) -> None:
    """Merge patch into the index. Additive — never removes existing entries.

    patch keys:
      columns: {col_name: {phase, how, intuition, caveat, dtype, summary}}
      tables:  {table_name: {path, summary, phase}}
      charts:  {chart_name: {path, finding, tier, phase}}
               tier: "finding" (show human) | "diagnostic" (audit trail only)
      concerns: [{phase, text}]
    """
    idx = read_index(dataset_id)
    for key in ("columns", "tables", "charts"):
        if key in patch:
            idx[key].update(patch[key])
    if "concerns" in patch:
        idx["concerns"].extend(patch["concerns"])
    _index_path(dataset_id).write_text(json.dumps(idx, indent=2))


# ── main/ identity files ──────────────────────────────────────────────────────

def load_main(filename: str) -> str:
    """Load a shared identity/config file from memory/main/."""
    path = MEMORY_DIR / "main" / filename
    return path.read_text() if path.exists() else ""
