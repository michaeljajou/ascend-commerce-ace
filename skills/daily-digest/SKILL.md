---
name: daily-digest
description: Post a 9 AM daily digest to the brand's Slack channel — interactions, answer rate, moderation flags, new members, upcoming deadlines.
version: 0.3.1
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
ONE command — it builds the digest AND posts the clean, brand-tagged text to Slack itself:
```
python ${HERMES_SKILL_DIR}/scripts/digest.py --hours 24 --deadline-days 7 --post
```
Then end your turn with only `[SILENT]`. Do NOT pipe the script's output anywhere yourself —
delivery is the script's job (piping the JSON into Slack is exactly the bug this prevents).

Contents: total interactions (answered vs escalated vs routed), answer rate, 👍/👎, moderation
actions, new members + how many are mid-onboarding, and upcoming deal deadlines.

## Pitfalls
- Never post the JSON output to Slack — `--post` sends only the human-readable text.
- **If the command fails** (non-zero exit, any error output): retry it ONCE; if it fails again,
  your final response must be the error text — **NEVER `[SILENT]` after a failure**. A silent
  failed digest looks identical to a successful one, and nobody finds out for days.
- **NEVER install packages, create virtualenvs, or touch the environment.** A missing module
  is a deployment bug — reporting it IS the successful outcome; a human fixes it in git.
  2026-07-23: the digest script (since fixed) crashed on a missing module and the agent spent
  its entire 12-call budget on pip/uv/sudo/venv attempts; the cron job was recorded as FAILED
  and the flailing buried the one line of error text that mattered.
- Never edit skill files or create cron jobs — run the one command and stop.
- Read-only: the digest never changes data; safe to re-run.
- If the window is quiet, post the digest anyway (zeros are informative) — don't skip.

## Verification
- The Slack post shows yesterday's counts; numbers match `metrics_since` for the window.
