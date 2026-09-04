---
name: get-campaigns
description: Pull the brand's ACTIVE campaigns/challenges live from its Discord channels (newest post in #campaigns / #challenges = active) plus the recent #announcements posts, where campaign notices also land. Grounding source of truth for anything currently running — never fabricate.
version: 0.2.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Get Campaigns (live grounding)

The team launches a campaign or challenge by **posting it in #campaigns / #challenges** — the
newest post in each channel IS the active one. Campaign notices — the Growi sign-up link, date
changes, weekly leaderboards — also land in **#announcements**, mixed in with unrelated posts.
This skill fetches all three live from Discord, so what's "currently running" never depends on
anyone updating a file.

## When to Use
- Any question about what campaign/challenge is running now, its deadline, prize, sign-up link,
  or how to join.
- Before composing a digest, reminder, or announcement that references the current campaign.
- Whenever `knowledge.yaml`'s campaign info might be stale — for "what's running now", this skill
  wins; `knowledge.yaml` remains the source for evergreen program rules (commission, samples, FAQ).

## Quick Reference
```
python3 ${HERMES_SKILL_DIR}/scripts/fetch.py                                  # campaigns + challenges + announcements
python3 ${HERMES_SKILL_DIR}/scripts/fetch.py --channels campaigns             # one channel
python3 ${HERMES_SKILL_DIR}/scripts/fetch.py --limit 20                       # more history
```

## Procedure
1. Run the script. Launch channels (`campaigns`, `challenges`) return `active` (the newest post —
   the running campaign/challenge) and `previous` (recent history, for "last challenge"
   questions). `announcements` returns `recent`: scan those posts for campaign notices — they are
   not ranked, and the newest one is usually about something else.
2. Answer **using only** the returned post text. Extract deadlines, prizes, sign-up links, and
   how-to-enter only as literally stated. `fetched_at` is now: compare it with the dates in a
   post before saying a campaign is running or has ended.
3. If `active` is `null` and no `recent` announcement covers the question, say nothing is
   currently posted and hand off to `escalate-to-team` if the creator needs an answer — do
   **not** guess or reuse old campaigns.

## Pitfalls
- The newest post is the active one **by convention** — do not second-guess it or prefer an older
  post that "looks more like" a campaign.
- **Webhook posts are team posts.** Brands post through a webhook (I Am Joy's "I Am Joy Brand")
  with the text inside an embed; the script reads embeds and keeps webhook posts. Non-webhook
  bots — Ace's own replies in the channel — are still excluded. Until 2026-09-04 webhook posts
  were treated as bots: on 2026-08-28 and 2026-09-03 `#campaigns` came back `active: null` with
  a live monthly campaign on the board, and Ace told two creators nothing was running.
- A post may list `attachments` (image URLs). The graphic usually repeats the details, but only
  the text is readable here — never invent what an image says; point the creator at the post.
- Details absent from the post (exact rates, dates) are absent, period → answer the covered part,
  escalate the rest. Never fill gaps from memory or from stale `knowledge.yaml` campaign entries.
- `previous` posts are context for history questions only — never present one as currently active.
- The script needs the profile's `channel_directory.json` (exists after the gateway's first
  Discord connect). If it errors, escalate rather than answering ungrounded.

## Verification
- With posts in #campaigns, the script's `active` matches the channel's newest team or webhook
  post, embed text included.
- With an empty channel, `active` is `null` and no campaign is invented.
- A campaign notice posted in #announcements appears under `announcements.recent`.
