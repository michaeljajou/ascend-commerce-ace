---
name: get-campaigns
description: Pull the brand's ACTIVE campaigns/challenges live from its Discord channels (newest post = active). Grounding source of truth for anything currently running — never fabricate.
version: 0.1.1
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Get Campaigns (live grounding)

The team launches a campaign or challenge by **posting it in #campaigns / #challenges** — the
newest post in each channel IS the active one. This skill fetches those posts live from Discord,
so what's "currently running" never depends on anyone updating a file.

## When to Use
- Any question about what campaign/challenge is running now, its deadline, prize, or how to join.
- Before composing a digest, reminder, or announcement that references the current campaign.
- Whenever `knowledge.yaml`'s campaign info might be stale — for "what's running now", this skill
  wins; `knowledge.yaml` remains the source for evergreen program rules (commission, samples, FAQ).

## Quick Reference
```
python ${HERMES_SKILL_DIR}/scripts/fetch.py                                   # campaigns + challenges
python ${HERMES_SKILL_DIR}/scripts/fetch.py --channels campaigns              # one channel
python ${HERMES_SKILL_DIR}/scripts/fetch.py --channels campaigns --limit 20   # more history
```

## Procedure
1. Run the script. Per channel it returns `active` (the newest post — the running
   campaign/challenge) and `previous` (recent history, for "last challenge" questions).
2. Answer **using only** the returned post content. Extract deadlines, prizes, and how-to-enter
   only as literally stated in the post.
3. If `active` is `null` (nothing posted), say nothing is currently posted and hand off to
   `escalate-to-team` if the creator needs an answer — do **not** guess or reuse old campaigns.

## Pitfalls
- The newest post is the active one **by convention** — do not second-guess it or prefer an older
  post that "looks more like" a campaign.
- Bot-authored messages (including Ace's own replies in the channel) are excluded automatically —
  the active post is the newest **human/team** post. If the team ever launches campaigns via a
  webhook/bot, that poster needs an exception here first.
- Details absent from the post (exact rates, dates) are absent, period → answer the covered part,
  escalate the rest. Never fill gaps from memory or from stale `knowledge.yaml` campaign entries.
- `previous` posts are context for history questions only — never present one as currently active.
- The script needs the profile's `channel_directory.json` (exists after the gateway's first
  Discord connect). If it errors, escalate rather than answering ungrounded.

## Verification
- With posts in #campaigns, the script's `active` matches the channel's newest message.
- With an empty channel, `active` is `null` and no campaign is invented.
