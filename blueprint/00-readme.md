# SaaS Blueprint System
<!-- READ 00-state.md FIRST, THEN THIS FILE -->

## What Is This

A template system that turns a SaaS idea into AI-ready blueprints.

**Input:** Human describes a SaaS idea.
**Output:** PRD, architecture, file tree, database schema, auth/payment flows,
test strategy, milestone plan, and self-generated AI rules (.cursorrules, CLAUDE.md).

## How to Use (For Humans)

1. Open a new AI session (Claude Code, Cursor, etc.)
2. Tell the AI: "Read all files in `saas-blueprint/`, starting with `00-state.md`"
3. The AI will know exactly where things stand and what to do next

## How to Use (For AI)

### Session Start Protocol

```
1. Read 00-state.md              → Where are we? What's done? What's next?
2. Read 00-game-rules.md         → How should I operate?
3. Read 00-variables.md          → What variables are set?
4. Read the current phase files  → What's the current context?
5. Resume from "What's Next" in 00-state.md
```

### Session End Protocol

```
1. Update 00-state.md (keep under 80 lines):
   - Update "Current Position"
   - Update "What's Next"
   - Rewrite "Handoff" section (3-5 sentences for next AI)
2. Append to 00-session-log.md:
   - Add new session entry at the bottom
   - If log exceeds 150 lines, compress oldest detailed entries to Archive
3. Update changelog.md with all file changes
4. Bump version headers on any modified 0x-*.md files
5. If a review gate was passed: create a save in saves/gate-N-description.md
```

### Save System

```
00-state.md          → Autosave (current state, always lean, max 80 lines)
00-session-log.md    → History (last 10 sessions detailed, older compressed)
saves/gate-N-*.md    → Checkpoints (permanent, max 5 slots, rollback points)
```

To roll back: tell the AI "load gate-N" and it will restore to that checkpoint.

### If Starting a Brand New SaaS Idea

```
1. Copy this entire saas-blueprint/ folder
2. Start at Phase 1: run 01-qna-script.md with the human
3. Follow the phase progression in 00-state.md
```

## File Map

| Prefix | Phase | Files |
|---|---|---|
| `00-` | Character Creation | game-rules, variables, state, session-log, readme |
| `01-` | Tutorial (PRD) | prd, qna-script, mvp-reduction-checklist |
| `02-` | World Map (Architecture) | stack, file-tree, auth-flow, payment-flow, api-routes, schema, pages-and-components, risk-registry, test-strategy |
| `03-` | Gameplay (Execution) | milestones, cursorrules, claude-md |
| (none) | Cross-cutting | changelog |
| `saves/` | Checkpoints | gate-0, gate-1, ... (max 5 permanent save slots) |

## Portability

This blueprint is **location-independent**. It can live anywhere.
The actual project code will be generated in a separate repo.

- `00-state.md` tracks both the blueprint location AND the project repo location
- When the project repo is created, the AI generates `.cursorrules` and `CLAUDE.md`
  from the `03-*.md` templates and places them in the project repo
- The blueprint remains the source of truth — if architecture changes,
  update the blueprint FIRST, then regenerate the project files

## The Variable System

All templates use `{{VARIABLE}}` placeholders.
`00-variables.md` is the single source of truth.

When a variable changes:
1. Update `00-variables.md`
2. Grep all `01-*.md` and `02-*.md` files
3. Update every occurrence
4. Log the change in `changelog.md`
