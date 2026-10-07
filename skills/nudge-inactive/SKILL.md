---
name: nudge-inactive
description: Gently nudge creators inactive ~48h after onboarding. Creators quiet longer than 7 days are left alone — nothing is posted to Slack.
version: 0.3.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
    blueprint:
      schedule: "0 10 * * *"   # daily 10:00
      prompt: "Run nudge-inactive: gently nudge 48h-inactive creators. End with only [SILENT]."
---

# Nudge Inactive

Keeps newly onboarded creators engaged. Daily cron.

## Feature policy
Use this skill only when `ace.features.engagement` is enabled. The script validates the policy
before reading creator activity. When disabled, do not scan activity or send post-completion
nudges. Incomplete onboarding reminders remain part of `run-onboarding`, not this skill.

## When to Use
Daily (blueprint). Acts only on creators who completed onboarding.

## Procedure
1. Select who is due:
   ```
   python ${HERMES_SKILL_DIR}/scripts/nudge.py --nudge-after-h 48 --max-inactive-h 168
   ```
   Output: `{"nudge": ["@..."]}`.
2. For each `nudge` handle → send a short, friendly DM/mention pointing to something easy to do
   (introduce themselves, join the current campaign). Ground specifics with `get-knowledge`.
3. End your turn with only `[SILENT]`.

This skill never posts to Slack. The 7-day "still inactive" team flag was removed on
2026-10-06: #ace-escalations holds only posts that need the team to act, and a creator who
drifted off is not one of them.

## Pitfalls
- Keep nudges light and infrequent — one per creator per run, never a barrage.
- Creators quiet for more than `--max-inactive-h` are not in the output and are left alone.
- Creators still mid-onboarding are excluded — finish onboarding first.

## Verification
- A creator inactive 48h–7d appears in `nudge`; one inactive >7d and a recently active one
  do not appear at all. Nothing reaches Slack.
