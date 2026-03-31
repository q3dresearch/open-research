---
title: Phase Registry
description: Single source of truth for all phase naming
---

# Phase Registry

**File**: `lib/artifacts.py:ACTIONS`

```python
ACTIONS = {
    "00": "vet",
    "10": "eda",
    "15": "clean",
    "20": "engineer",
    "25": "cluster",
    "30": "select",
    "50": "report",
}
ACTION_CODES = {v: k for k, v in ACTIONS.items()}  # reverse lookup
```

## Usage in agents

All agents derive their constants from the registry:

```python
from lib.artifacts import ACTION_CODES, action_dir

ACTION = "engineer"
ACTION_CODE = ACTION_CODES[ACTION]           # "20"
PHASE_DIR = action_dir(ACTION_CODE, ACTION)  # "20-engineer"
PROMPT_NAME = f"research-{ACTION_CODE}-{ACTION}"  # "research-20-engineer"
```

Never hardcode:

```python
# WRONG
PHASE_DIR = "20-engineer"
PROMPT_NAME = "research-20-engineer"

# RIGHT
PHASE_DIR = action_dir(ACTION_CODES["engineer"], "engineer")
```

## Cross-phase references

When one agent needs to load another phase's artifacts:

```python
CLEAN_DIR = action_dir(ACTION_CODES["clean"], "clean")
ENGINEER_DIR = action_dir(ACTION_CODES["engineer"], "engineer")
CLUSTER_DIR = action_dir(ACTION_CODES["cluster"], "cluster")
```

## Adding a new phase

1. Insert into `ACTIONS` in `lib/artifacts.py` (leave gaps of 10 for future insertion)
2. Create `agents/{action}.py` following existing agent patterns
3. Create `configs/prompts/research-{code}-{action}.md`
4. Add flag definitions to `lib/flags.py:FLAG_CATALOG`
5. Update `CLAUDE.md` and `docs/`
