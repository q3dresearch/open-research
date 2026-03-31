#!/usr/bin/env python3
"""Generate llms.txt and llms-full.txt for LLM consumption.

llms.txt    — index of all doc pages (titles + URLs)
llms-full.txt — full content of all doc pages concatenated

Both go into docs/ so mkdocs serves them at /llms.txt and /llms-full.txt.
Mintlify serves them automatically from the same paths.

Run: python scripts/build_llms_txt.py
"""

from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
SITE_URL = "https://q3dresearch.github.io/open-research"

# Doc pages in order of importance
PAGES = [
    ("index.md", "q3d Open Research — Overview"),
    ("architecture.md", "Pipeline Architecture & DAG"),
    ("phases.md", "Phase Reference"),
    ("flags.md", "Flag System (Route Unlocking)"),
    ("guides/loading-datasets.md", "Guide: Loading Datasets"),
    ("guides/human-notes.md", "Guide: Human Notes"),
    ("guides/running-locally.md", "Guide: Running Locally"),
    ("reference/phase-registry.md", "Reference: Phase Registry"),
    ("reference/artifacts.md", "Reference: Artifact Structure"),
    ("reference/prompts.md", "Reference: LLM Prompts"),
]


def md_to_url(path: str) -> str:
    """Convert doc path to URL."""
    url = path.replace(".md", "/").replace("index/", "")
    return f"{SITE_URL}/{url}"


def build_llms_txt():
    """Build index file."""
    lines = [
        "# q3d Open Research Documentation",
        "",
        "> Autonomous AI research pipeline over public datasets.",
        "> Seven phases: vet → eda → clean → engineer → cluster → select → report",
        "",
    ]
    for path, title in PAGES:
        url = md_to_url(path)
        lines.append(f"- [{title}]({url})")

    out = DOCS_DIR / "llms.txt"
    out.write_text("\n".join(lines))
    print(f"Written: {out}")


def build_llms_full_txt():
    """Build full content file."""
    sections = []
    for path, title in PAGES:
        md_path = DOCS_DIR / path
        if not md_path.exists():
            print(f"  Skipping (not found): {path}")
            continue
        content = md_path.read_text()
        # Strip frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                content = content[end + 3:].lstrip()
        sections.append(f"# {title}\n\n{content}")

    combined = "\n\n---\n\n".join(sections)
    out = DOCS_DIR / "llms-full.txt"
    out.write_text(combined)
    print(f"Written: {out} ({len(combined):,} chars)")


if __name__ == "__main__":
    build_llms_txt()
    build_llms_full_txt()
