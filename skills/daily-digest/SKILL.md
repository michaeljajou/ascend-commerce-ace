---
name: daily-digest
description: Post a 9 AM daily digest to the brand's Slack channel — interactions, answer rate, moderation flags, new members, upcoming deadlines.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
    blueprint:
      schedule: "0 9 * * *"   # daily 09:00 → Slack
      deliver: slack
      prompt: "Build and post the daily digest to the brand Slack channel using daily-digest."
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
2. Post the `text` to the brand Slack channel (Hermes delivers `slack`).

Contents: total interactions (answered vs escalated vs routed), answer rate, 👍/👎, moderation
actions, new members + how many are mid-onboarding, and upcoming deal deadlines.

## Pitfalls
- Read-only: the digest never changes data; safe to re-run.
- If the window is quiet, post the digest anyway (zeros are informative) — don't skip.

## Verification
- The Slack post shows yesterday's counts; numbers match `metrics_since` for the window.
