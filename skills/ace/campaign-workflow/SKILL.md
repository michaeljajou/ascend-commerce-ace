---
name: campaign-workflow
description: Announcement Type 2 — gather campaign/challenge specifics from the team in Slack, draft for approval, then post to Discord on approval.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Campaign Workflow (Announcement Type 2)

Campaign/challenge announcements are unique each time, so the team supplies the specifics. This
runs a Slack-mediated draft → approve → post flow.

## When to Use
~3 days before a campaign/challenge is scheduled to launch (team-scheduled or calendar-triggered).

## Procedure
1. **Open a Slack thread** in the brand channel and prompt the team for the specifics you need:
   campaign name, theme, prizes, rules, deadline, target Discord channel(s), launch time.
2. **Collect** the team's replies from the thread (Hermes reads the thread).
3. **Draft** the announcement in the brand voice and **post the draft in the thread for review**.
4. **On approval** (team reaction/keyword), **post to the configured Discord channel(s)** at the
   scheduled launch time. If asked, also schedule it via cron.

## Pitfalls
- Do not post to Discord until the team explicitly approves in the thread.
- Use only the details the team provided; don't pad with invented prizes/rules.
- One thread per campaign; keep the prompt checklist tight so the team can fill it fast.

## Verification
- The thread captures all required fields; the approved draft posts to the right Discord channel at the right time.
