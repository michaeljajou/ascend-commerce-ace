---
name: detect-sentiment
description: Classify a message into a moderation category (negative sentiment, policy violation, scam, off-topic) or none, in monitored/active channels.
version: 0.1.0
author: Ascend Commerce
license: MIT
---

# Detect Sentiment

The detection step that feeds moderation. Pure reasoning — read a message and label it. Acting on
the label is `moderate-message`'s job.

## When to Use
On messages in active channels (community-chat etc.) and, read-only, in MONITOR_ONLY channels
(via `monitor-channel`).

## Categories
- `negative_sentiment` — frustration about payments, shipping, the brand
- `policy_violation` — spam, self-promotion, inappropriate content
- `scam` — fake brand reps, phishing links, impersonation (also: `phishing`, `impersonation`, `severe`)
- `off_topic` — disruptive / off-topic content
- `none` — nothing to act on (the common case)

## Procedure
1. Read the message (+ recent context).
2. Output exactly one category, or `none`.
3. If not `none`, hand the category to `moderate-message` (and in MONITOR_ONLY channels, never reply publicly — escalate per `monitor-channel`).

## Pitfalls
- Be conservative: ordinary venting is usually `negative_sentiment` (Friendly tier), not a violation.
- A link from an unknown account asking for credentials/DMs is `scam` — do not downgrade it.
- Don't act here; only label. `moderate-message` owns the tier + action.

## Verification
- Frustration → `negative_sentiment`; phishing link → `scam`; normal chat → `none`.
