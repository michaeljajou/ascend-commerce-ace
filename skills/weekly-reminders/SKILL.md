---
name: weekly-reminders
description: Announcement Type 1 — automated recurring reminders for creators to join active campaigns/challenges. No human input.
version: 0.2.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
    blueprint:
      schedule: "0 16 * * 1,4"   # Mondays & Thursdays 16:00
      prompt: "Post the recurring campaign/challenge reminder to the configured channel using weekly-reminders."
---

# Weekly Reminders (Announcement Type 1)

Fully automated nudges to participate in the active campaign/challenge. Twice weekly, no human in
the loop — the details come from the knowledge base.

## When to Use
On the blueprint schedule (Mon & Thu by default). `setup-brand` points the cron's delivery at the
brand's POST_ANSWER/POST_ONLY channel.

## Procedure
1. Pull the current campaign/challenge live from Discord (newest team post = active):
   ```
   python ${HERMES_SKILL_DIR}/../get-campaigns/scripts/fetch.py
   ```
2. Fill a short reminder template (name, theme, how to participate, deadline, prizes) **using only**
   facts from the `active` posts.
3. Post to the configured channel (Hermes cron delivery handles the target).

## Pitfalls
- If `active` is null in both channels, **don't invent one** — skip the post (or post a generic
  "join the community" nudge only if the brand allows).
- Never state prizes/deadlines not present in the active post.

## Verification
- On schedule, a reminder posts to the configured channel with details matching the newest
  campaign/challenge posts.
