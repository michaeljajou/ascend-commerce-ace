---
name: weekly-reminders
description: Announcement Type 1 — automated recurring reminders for creators to join active campaigns/challenges. No human input.
version: 0.4.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
    blueprint:
      schedule: "0 16 * * 1,4"   # Mondays & Thursdays 16:00
      deliver: discord           # the HOME channel — post.py puts the reminder in #announcements
      prompt: "Post the recurring campaign/challenge reminder following the weekly-reminders skill exactly: fetch.py for the active campaign, compose the reminder, hand it to post.py on stdin. End with only [SILENT]."
---

# Weekly Reminders (Announcement Type 1)

Fully automated nudges to participate in the active campaign/challenge. Twice weekly, no human in
the loop — the details come live from the brand's launch channels.

## When to Use
On the blueprint schedule (Mon & Thu by default), as the `weekly-reminders` cron job.

## Procedure
1. Pull the current campaign/challenge live from Discord (newest team post = active):
   ```
   python3 ${HERMES_SKILL_DIR}/../get-campaigns/scripts/fetch.py
   ```
2. Compose a short reminder (name, theme, how to participate, deadline, prizes) **using only**
   facts from the `active` posts. Under 2000 characters. No date/data recap, no "here's the
   reminder", no `---` separators, no notes about closed challenges — the text is posted
   verbatim.
3. Post it with the script, text on stdin inside a quoted heredoc:
   ```
   python3 ${HERMES_SKILL_DIR}/scripts/post.py --stdin <<'EOF'
   🔥 **<reminder>** …
   EOF
   ```
   It resolves the brand's announcement channel itself (never pass `--channel-id`), pings
   nobody, and prints `{"posted": …}`. Exit code 2 means it already posted there within the
   hour: stop — do not retry, do not `--force`.
4. Reply with exactly `[SILENT]` and nothing else. The job delivers to the private home
   channel, and a good run must deliver nothing. If nothing is active, skip step 3 and still
   reply `[SILENT]`.

## Pitfalls
- If `active` is null in both launch channels, **don't invent one** — skip the post.
  `announcements.recent` is context, not a launch: it may confirm a campaign is still
  running, never define one.
- Never state prizes/deadlines not present in the active post.
- Never put the reminder in your reply. Anything other than `[SILENT]` lands in the home
  channel — harmless, but noise. Before 2026-09-22 the reply WAS the post, and every reminder
  reached creators wrapped in Hermes' "Cronjob Response" boilerplate plus the agent's preamble.

## Why the script posts, not the cron delivery
Hermes has one delivery target per cron job and always delivers a failed run's error summary
to it. While this job delivered straight into `#announcements`, the 2026-09-21 run's
`HTTP 402` (OpenRouter balance) landed in front of QBounce's and Prime Natural's creators.
With `--deliver discord` (the home channel, `#agent-ace`) a failure is only ever seen by the
team, and `post.py` is the only path into the public channel.

## Verification
- On schedule, a reminder posts to the announcement channel with details matching the newest
  campaign/challenge posts, and nothing around it: no header, footer or preamble.
- `hermes --profile <brand> cron list --all` shows the job with `Deliver: discord` and
  `Last run … ok`; the home channel stays quiet on a good run.
- `python3 post.py --profile-dir <profile> --dry-run --text x` resolves `channel` to the
  brand's POST_* channel and its id. Needs `channel_directory.json`, i.e. one gateway connect.
