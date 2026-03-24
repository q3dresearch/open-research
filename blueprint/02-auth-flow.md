# Auth Flow
<!-- version: 0.1 | phase: 2 | last-updated: 2026-03-25 -->

## N/A — No Web App

This project is a CLI/agent pipeline, not a web application. There is no user authentication.

### Access Control

| Actor | Access mechanism | Scope |
|---|---|---|
| Operator | Git repo access + local CLI | Full control: run agents, review decisions, override verdicts |
| AI agent | Claude API key in `.env` | Execute pipeline steps, commit to branches, open PRs |
| Consumer | Public GitHub repo (open-research) | Read-only: browse artifacts, DB, notebooks |

### Security

- Claude API key stored in `.env` (gitignored)
- `.env.example` provided as template (no real keys)
- Agents never expose the API key in logs or committed files
- `lib/llm.py` strips API key from any error messages before logging
