---
name: nudge-inactive
description: Gently nudge creators inactive ~48h after onboarding; flag still-inactive creators (7d) to the team in Slack.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
    blueprint:
      schedule: "0 10 * * *"   # daily 10:00
      prompt: "Run nudge-inactive: gently nudge 48h-inactive creators and flag 7d-inactive ones to the team."
---

# Nudge Inactive

Keeps newly onboarded creators engaged. Daily cron.

## When to Use
Daily (blueprint). Acts only on creators who completed onboarding.

## Procedure
1. Compute buckets:
   ```
   python ${HERMES_SKILL_DIR}/scripts/nudge.py --nudge-after-h 48 --flag-after-h 168
   ```
   Output: `{"nudge": ["@..."], "flag": ["@..."]}`.
2. For each `nudge` handle → send a short, friendly DM/mention pointing to something easy to do
   (introduce themselves, join the current campaign). Ground specifics with `get-knowledge`.
3. For each `flag` handle → post a brief note in the brand Slack channel so the team can reach out.

## Pitfalls
- Keep nudges light and infrequent — one per creator per run, never a barrage.
- `flag` creators are not also nudged (the script already excludes them).
- Creators still mid-onboarding are excluded — finish onboarding first.

## Verification
- A creator inactive 48h–7d appears in `nudge`; one inactive >7d appears in `flag`; recently active creators appear in neither.
