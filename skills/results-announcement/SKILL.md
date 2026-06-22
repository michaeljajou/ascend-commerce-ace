---
name: results-announcement
description: Announcement Type 3 — pull campaign/challenge results from Growi, post winners to Discord, and congratulate in #success-stories.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
    blueprint:
      schedule: "0 17 * * *"   # daily check; posts only when a campaign has ended
      prompt: "Check Growi for newly-ended campaigns; if results are available, post them with results-announcement."
---

# Results Announcement (Announcement Type 3)

When a campaign/challenge ends, pull results from Growi and announce them.

## When to Use
On the daily check (blueprint), or when the team signals a campaign has ended.

## Procedure
1. Build the announcement from Growi:
   ```
   python ${HERMES_SKILL_DIR}/scripts/results.py --base-url <growi_url> --project <growi_project>
   ```
   Returns a ready-to-post `text` (winners, top performers, stats).
2. Post it to the configured results/announcements Discord channel.
3. Post congratulations to **#success-stories** as well.

## Pitfalls
- Only post once per campaign — don't repeat the same results on subsequent daily checks.
- If Growi has no results yet, do nothing (no partial/placeholder announcements).
- Winner handles/prizes come from Growi; never edit or invent them.

## Verification
- Ended campaign → a winners post in the results channel + a congrats post in #success-stories, matching Growi.
