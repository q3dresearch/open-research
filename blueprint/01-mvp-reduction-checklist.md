# MVP Reduction Checklist
<!-- version: 0.1 | phase: 1 | last-updated: YYYY-MM-DD -->

<!--
  INSTRUCTIONS FOR AI:
  Run this checklist AFTER the Q&A is complete but BEFORE starting Phase 2.
  For every question, the default answer should be "no" unless the human
  provides a strong justification. Your job is to keep the MVP minimal.

  If the answer is "yes" — document WHY in the justification column.
  If the answer is "no" — the feature goes to "Explicitly Out of Scope" in 01-prd.md.
-->

## The Golden Rule

> Can {{TARGET_USER}} get value from {{PROJECT_NAME}} without this feature?
> If yes → cut it from MVP.

## Complexity Audit

| Question | Answer | Justification (if yes) | Impact if cut |
|---|---|---|---|
| Can this be done **without real-time**? (use polling or refresh instead) | | | |
| Can this be done **without background jobs**? (use synchronous processing) | | | |
| Can this be done **without caching**? (accept slower reads for now) | | | |
| Can this be done **without an admin panel**? (use DB GUI or scripts) | | | |
| Can this be done **without file uploads**? (use links or text instead) | | | |
| Can this be done **without full-text search**? (use simple filters) | | | |
| Can this be done **without email notifications**? (use in-app only) | | | |
| Can this be done **without multiple user roles**? (one role for v1) | | | |
| Can this be done **without multi-tenancy**? (single namespace for v1) | | | |
| Can this be done **without OAuth/social login**? (email+password only) | | | |
| Can this be done **without a mobile-responsive design**? (desktop-first) | | | |
| Can this be done **without third-party integrations**? (manual for now) | | | |
| Can this be done **without usage analytics**? (add tracking later) | | | |
| Can this be done **without onboarding flows**? (simple landing → dashboard) | | | |
| Can this be done **with only 1 subscription tier**? (add tiers later) | | | |

## Feature Kill Count

- **Features entering checklist:** ___
- **Features surviving checklist:** ___
- **Features cut:** ___

> Target: Cut at least 40% of proposed features from MVP.

## Survived Features → MVP Scope

<!--
  AI INSTRUCTION: List ONLY the features that survived the checklist.
  These get copied into 01-prd.md "In Scope" section.
-->

1.
2.
3.

## Cut Features → Post-MVP Backlog

<!--
  AI INSTRUCTION: List features that were cut.
  These get copied into 01-prd.md "Explicitly Out of Scope" section.
  Tag each with a rough priority for when to add them back.
-->

| Feature | Why Cut | Add Back In |
|---|---|---|
| | | v1.1 / v1.2 / v2.0 / maybe-never |
| | | |
| | | |
