# Pages & Components
<!-- version: 0.1 | phase: 2 | last-updated: 2026-03-25 -->

## N/A — No Web UI

This project has no web interface. The operator interacts via:

### Interfaces

| Interface | Tool | Use case |
|---|---|---|
| CLI | `python agents/*.py` | Run agents, trigger pipeline steps |
| SQLite browser | DB Browser for SQLite, `sqlite3` CLI, Datasette (future) | Inspect game state, review datasets, query runs |
| File browser | VS Code, GitHub | Read notebooks, charts, decision logs in `artifacts/` |
| Git | `git log`, `git diff`, GitHub PRs | Review AI-generated artifacts, track changes |
| Jupyter | `jupyter notebook` | Open and inspect executed notebooks in `artifacts/` |

### Future (P2+)

If a web UI is ever built, it would be a read-only dashboard over the SQLite DB:
- Dataset explorer (filter by level, portal, graduation status)
- Run timeline (per dataset)
- Chart gallery (graduated datasets)
- Cost dashboard

Candidate: Datasette (zero-config web UI for SQLite) or a simple static site generator reading from the DB.
