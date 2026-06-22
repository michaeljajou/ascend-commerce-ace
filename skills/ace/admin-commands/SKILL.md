---
name: admin-commands
description: Operator/admin actions — force a KB refresh, view metrics, and trigger ad-hoc announcements. Team-only.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Admin Commands

Team-facing operations. Restrict to operators (Hermes command access control) — these are not for creators.

## When to Use
When an authorized operator issues an admin action.

## Actions
- **`/ace update`** — force a knowledge-base refresh now:
  ```
  python ${HERMES_SKILL_DIR}/../ingest-knowledge/scripts/ingest.py --source <drive_folder>
  ```
- **metrics** — show recent metrics:
  ```
  python ${HERMES_SKILL_DIR}/../daily-digest/scripts/digest.py --hours 24
  ```
- **`/ace announce`** — post an ad-hoc announcement → delegate to `post-announcement` (one brand or all).
- **configure** — channel behavior / schedules live in the profile config; re-run `setup-brand`
  to re-apply from an updated spec.
- **add/remove brand** — adding a brand is `setup-brand` in a new profile; removing is a Hermes
  profile-level operation.

## Pitfalls
- Gate every action to operators; never expose `/ace announce` or `/ace update` to creators.
- `/ace update` is idempotent; safe to run anytime after the brand team edits Drive.

## Verification
- `/ace update` reports documents/chunks ingested; metrics returns current counts; `/ace announce` posts to the requested target(s).
