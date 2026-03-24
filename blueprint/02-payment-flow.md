# Payment Flow
<!-- version: 0.1 | phase: 2 | last-updated: 2026-03-25 -->

## N/A — No Monetization

This is an open research pipeline. No payments, no subscriptions.

### Cost Tracking (Internal)

The only costs are Claude API usage. Tracked per-run in `runs.cost_estimate_usd`.

| Cost control | Implementation |
|---|---|
| Per-run tracking | `lib/llm.py` estimates token cost, stored in runs table |
| Daily budget cap | Director agent checks cumulative daily spend before dispatching |
| Hard limit | Configurable in `portals.yaml` as `daily_budget_usd` |
| Weekly review | Operator queries: `SELECT SUM(cost_estimate_usd) FROM runs WHERE started_at > date('now', '-7 days')` |
