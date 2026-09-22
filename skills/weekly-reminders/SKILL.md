---
name: weekly-reminders
description: Announcement Type 1 — automated recurring reminders for creators to join active campaigns/challenges. No human input.
version: 0.3.0
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
   python3 ${HERMES_SKILL_DIR}/../get-campaigns/scripts/fetch.py
   ```
2. Fill a short reminder template (name, theme, how to participate, deadline, prizes) **using only**
   facts from the `active` posts.
3. Post to the configured channel (Hermes cron delivery handles the target). **Your whole
   final response is delivered verbatim as the post.** Output ONLY the reminder text: no
   date/data recap, no "here's the reminder", no `---` separators, no notes about closed
   challenges. If nothing is active, respond with exactly `[SILENT]` and nothing else.

## Pitfalls
- If `active` is null in both launch channels, **don't invent one** — skip the post (or post a
  generic "join the community" nudge only if the brand allows). `announcements.recent` is
  context, not a launch: it may confirm a campaign is still running, never define one.
- Never state prizes/deadlines not present in the active post.

## Verification
- On schedule, a reminder posts to the configured channel with details matching the newest
  campaign/challenge posts, and nothing but the reminder appears there.
- The cron job's delivery target is the numeric channel id (`discord:<id>`, written by
  `resolve_channels.py`). A `discord:#name` target only delivers when the channel name is
  undecorated — on servers with names like `📢│announcements` it 404s on every run while
  `cron list` still says "ok" (I Am Joy, Aug–Sep 2026).
- The brand config has `cron.wrap_response: false` (forced by `setup-brand`). With Hermes'
  default the post arrives as `Cronjob Response: weekly-reminders (job_id: …)` + the text +
  `To stop or manage this job, send me a new message…`; QBounce and Prime Natural creators
  saw that wrapper on every reminder 2026-09-10 → 09-21.
- A failed run still delivers its error summary to this same channel — Hermes has one
  target per job and always delivers failures. The 2026-09-21 run posted an `HTTP 402`
  notice into both brands' `#announcements`. Keeping errors private means the job must
  deliver to the home channel and a script must post the reminder instead.
