---
name: daily-digest
description: Post a 9 AM daily digest to the brand's Slack channel — interactions, answer rate, moderation flags, new members, upcoming deadlines.
version: 0.2.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
    blueprint:
      schedule: "0 9 * * *"   # daily 09:00 → Slack (the skill posts via slack_cli.py itself)
      deliver: null
      prompt: "Build and post the daily digest to the team Slack channel using daily-digest. End with only [SILENT]."
---

# Daily Digest

A once-a-day summary for the team, posted to the brand's Slack channel.

## When to Use
Daily at 9 AM (blueprint, delivered to Slack).

## Procedure
1. Build it:
   ```
   python ${HERMES_SKILL_DIR}/scripts/digest.py --hours 24 --deadline-days 7
   ```
   Output includes a ready-to-post `text` plus the structured `digest`.
2. Post the `text` to the team Slack channel (the script brand-tags it automatically):
   ```
   python ${HERMES_SKILL_DIR}/../_lib/slack_cli.py post --stdin   # pipe the digest text in
   ```

Contents: total interactions (answered vs escalated vs routed), answer rate, 👍/👎, moderation
actions, new members + how many are mid-onboarding, and upcoming deal deadlines.

## Pitfalls
- Read-only: the digest never changes data; safe to re-run.
- If the window is quiet, post the digest anyway (zeros are informative) — don't skip.

## Verification
- The Slack post shows yesterday's counts; numbers match `metrics_since` for the window.
