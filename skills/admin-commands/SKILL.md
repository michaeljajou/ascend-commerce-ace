---
name: admin-commands
description: Operator/admin actions — check the brand knowledge file, view metrics, and trigger ad-hoc announcements. Team-only.
version: 0.2.0
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
- **knowledge** — the brand's knowledge is a YAML file in the profile that the team edits directly;
  it's read live, so there is **no ingest/refresh step**. Smoke-check it loads:
  ```
  python ${HERMES_SKILL_DIR}/../get-knowledge/scripts/get.py --section brand
  ```
- **metrics** — show recent metrics:
  ```
  python ${HERMES_SKILL_DIR}/../daily-digest/scripts/digest.py --hours 24
  ```
- **`/ace announce`** — post an ad-hoc announcement → delegate to `post-announcement` (one brand or all).
- **onboarding** — team controls for the creator onboarding flow (`ONBOARD = ${HERMES_SKILL_DIR}/../run-onboarding/scripts/onboarding.py`):
  ```
  python $ONBOARD status  --handle "@creator"    # step, retries, timestamps
  python $ONBOARD reset   --handle "@creator"    # back to the start (redo / rejoined)
  python $ONBOARD resolve --handle "@creator"    # close an escalated case by hand
  python $ONBOARD test-mode on|off               # compressed timers for QA on this server
  python $ONBOARD stats                          # completion / nudge / escalation metrics
  ```
  Creator data (TikTok, email, phone) syncs to the team's Google Sheet automatically at
  completion. To pull it directly or re-sync after a sheet outage:
  ```
  python ${HERMES_SKILL_DIR}/../run-onboarding/scripts/export_creators.py --out /tmp/creators.csv
  python ${HERMES_SKILL_DIR}/../run-onboarding/scripts/export_creators.py --push
  ```
  Ad-hoc nudge outside the schedule: compose it per `run-onboarding` Nudge mode and send with
  `run-onboarding/scripts/send_dm.py`. The whole flow's master switch is
  `ace.onboarding.enabled` in the profile config (flip + restart the gateway).
- **configure** — channel behavior / schedules live in the profile config; re-run `setup-brand`
  to re-apply from an updated spec.
- **add/remove brand** — adding a brand is `setup-brand` in a new profile; removing is a Hermes
  profile-level operation.

## Pitfalls
- Gate every action to operators; never expose `/ace announce` to creators.
- No "refresh" is needed — editing the knowledge YAML in the profile takes effect on the next read.

## Verification
- The knowledge smoke-check returns the brand section; metrics returns current counts; `/ace announce` posts to the requested target(s).
