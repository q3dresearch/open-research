"""Write structured markdown run artifacts for audit trails."""

import json
from datetime import datetime, timezone
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"

# ---------------------------------------------------------------------------
# Action registry — single source of truth for phase naming
# ---------------------------------------------------------------------------
# action_code → action name.  Codes use gaps of 10 for easy insertion.
ACTIONS = {
    "00": "vet",
    "10": "eda",
    "15": "clean",
    "20": "engineer",
    "25": "cluster",
    "30": "select",
    "50": "report",
}
ACTION_CODES = {v: k for k, v in ACTIONS.items()}  # action name → code


def action_dir(action_code: str, action: str) -> str:
    """Return the canonical directory name for a phase, e.g. '20-engineer'."""
    return f"{action_code}-{action}"


def _ensure_dirs(dataset_id: str) -> Path:
    """Create artifacts/{dataset_id}/ dir."""
    base = ARTIFACTS_DIR / dataset_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def write_run_artifact(
    *,
    run_id: str,
    dataset_id: str,
    action: str,
    action_code: str,
    agent: str,
    model: str,
    title: str,
    verdict: str,
    steps: list[dict],
    prompt_text: str,
    llm_response: dict,
    context: str = "",
    charts: list[dict] | None = None,
    chart_subdir: str = "charts",
    output_dir: Path | None = None,
) -> Path:
    """Write a structured markdown artifact for a run.

    Args:
        action: semantic phase name (vet, eda, engineer, select, report)
        action_code: sortable code (00, 10, 20, 30, 50)
        steps: list of {"name": str, "detail": str} describing what was executed
        prompt_text: the full prompt sent to the LLM
        llm_response: the parsed JSON response from the LLM
        context: any prior-run context carried forward
        charts: list of {"filename": str, "description": str} for generated charts
        chart_subdir: relative path from artifact base to chart dir (e.g. "charts/run01")
    """
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        base = output_dir
    else:
        base = _ensure_dirs(dataset_id)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    filename = f"{action_code}-{action}-{run_id}.md"
    path = base / filename

    ACTION_LABELS = {"vet": "Schema Vet", "eda": "EDA Analysis",
                     "engineer": "Deep Analysis", "select": "Feature Selection",
                     "report": "Research Report"}
    phase_label = ACTION_LABELS.get(action, action.title())

    lines = [
        "---",
        f"run_id: {run_id}",
        f"dataset_id: {dataset_id}",
        f"action: {action}",
        f"action_code: {action_code}",
        f"agent: {agent}",
        f"verdict: {verdict}",
        f"model: {model}",
        f"timestamp: {now}",
        "---",
        "",
        f"# {phase_label}: {title}",
        "",
    ]

    # Context from prior runs
    if context:
        lines += ["## Context", "", context, ""]

    # Steps executed
    lines += ["## Steps Executed", ""]
    for i, step in enumerate(steps, 1):
        lines.append(f"{i}. **{step['name']}** — {step['detail']}")
    lines.append("")

    # Full prompt (collapsible)
    lines += [
        "## Prompt Sent",
        "",
        "<details><summary>Full prompt</summary>",
        "",
        "```",
        prompt_text,
        "```",
        "",
        "</details>",
        "",
    ]

    # LLM response
    lines += [
        "## LLM Response",
        "",
        "```json",
        json.dumps(llm_response, indent=2),
        "```",
        "",
    ]

    # Charts section
    if charts:
        chart_items = [c for c in charts if c.get("filename")]
        if chart_items:
            lines += ["## Charts Generated", ""]
            for c in chart_items:
                lines.append(f"![{c['description'][:60]}]({chart_subdir}/{c['filename']})")
                lines.append(f"_{c['description']}_")
                lines.append("")

    # Extract key sections from response for quick reading
    if llm_response.get("reason"):
        lines += ["## Summary", "", llm_response["reason"], ""]

    if llm_response.get("research_angles"):
        lines += ["## Research Angles", ""]
        for a in llm_response["research_angles"]:
            lines.append(f"- {a}")
        lines.append("")

    if llm_response.get("key_findings"):
        lines += ["## Key Findings", ""]
        for f in llm_response["key_findings"]:
            lines.append(f"- {f}")
        lines.append("")

    if llm_response.get("research_questions"):
        lines += ["## Research Questions", ""]
        for q in llm_response["research_questions"]:
            lines.append(f"- {q}")
        lines.append("")

    if llm_response.get("chart_suggestions"):
        lines += ["## Chart Suggestions", ""]
        for c in llm_response["chart_suggestions"]:
            lines.append(f"- **{c.get('type', '?')}**: {c.get('description', '')}")
        lines.append("")

    if llm_response.get("feature_engineering"):
        lines += ["## Feature Engineering Ideas", ""]
        for fe in llm_response["feature_engineering"]:
            lines.append(f"- {fe}")
        lines.append("")

    if llm_response.get("concerns"):
        lines += ["## Concerns", ""]
        for c in llm_response["concerns"]:
            lines.append(f"- {c}")
        lines.append("")

    # Human notes placeholder
    lines += [
        "## Human Notes",
        "",
        "_(edit this section to add observations for future agents)_",
        "",
    ]

    path.write_text("\n".join(lines))
    return path


def ensure_human_notes(dataset_id: str, title: str) -> Path:
    """Create human-notes.md for a dataset if it doesn't exist."""
    base = _ensure_dirs(dataset_id)
    path = base / "human-notes.md"
    if not path.exists():
        path.write_text(
            f"# Human Notes: {title}\n"
            f"\n"
            f"## Better approaches discovered\n"
            f"\n"
            f"_(add observations about what worked better for this dataset)_\n"
            f"\n"
            f"## Context an agent wouldn't know\n"
            f"\n"
            f"_(domain knowledge, policy changes, data quirks)_\n"
        )
    return path


def load_human_notes(dataset_id: str) -> str | None:
    """Load human notes for a dataset, if they exist and have content."""
    path = ARTIFACTS_DIR / dataset_id / "human-notes.md"
    if not path.exists():
        return None
    text = path.read_text()
    # Check if it's still just the empty template
    if "_(add observations" in text and "_(domain knowledge" in text:
        return None
    return text


def load_prior_artifacts(dataset_id: str, before_action_code: str) -> str:
    """Load prior run artifacts as context for the next phase.

    Args:
        before_action_code: only include phases with code < this value
            (e.g. '30' loads 00-vet, 10-eda, 20-engineer artifacts)

    Returns a combined string of all prior artifacts plus human notes.
    """
    base = ARTIFACTS_DIR / dataset_id
    if not base.exists():
        return ""

    sections = []

    # Flat artifacts in dataset root: {code}-{action}-{run_id}.md
    artifact_files = sorted(base.glob("[0-9][0-9]-*.md"))
    for af in artifact_files:
        # Parse action_code from filename: 00-vet-{run_id}.md -> '00'
        code = af.stem[:2]
        if code >= before_action_code:
            continue
        content = af.read_text()
        # Strip collapsible prompt blocks to save tokens
        lines = content.split("\n")
        filtered = []
        in_details = False
        for line in lines:
            if "<details>" in line:
                in_details = True
                filtered.append("_(full prompt omitted — see artifact file)_")
                continue
            if "</details>" in line:
                in_details = False
                continue
            if not in_details:
                filtered.append(line)
        sections.append("\n".join(filtered))

    # Append human notes
    notes = load_human_notes(dataset_id)
    if notes:
        sections.append(f"---\n\n{notes}")

    return "\n\n---\n\n".join(sections)
