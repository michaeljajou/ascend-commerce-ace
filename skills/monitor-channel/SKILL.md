---
name: monitor-channel
description: Watch MONITOR_ONLY channels (e.g. success-stories) for sentiment without ever replying publicly; escalate concerns to Slack only.
version: 0.1.0
author: Ascend Commerce
license: MIT
---

# Monitor Channel

For MONITOR_ONLY channels (default: `success-stories`). Ace **reads** for sentiment but **never
posts** in the channel. Anything noteworthy goes to the team in Slack, not the public channel.

> Wiring note: how Hermes lets a profile *read but not reply* in a channel is a Phase 0 spike item
> (channel scoping vs a read-only hook). This skill encodes the behavior regardless of mechanism.

## When to Use
On messages in any channel mapped to MONITOR_ONLY (from `setup-brand`'s channel scoping `monitor` list).

## Procedure
1. Run `detect-sentiment` on the message.
2. **Never reply in the channel.** No reactions, no posts — keep it pristine.
3. If a concern is detected (negativity, scam, violation): escalate to the brand Slack channel via
   `escalate-to-team` with context. For scams, also flag for deletion per `moderate-message`.
4. Positive content (success stories) needs no action — it's left to shine.

## Pitfalls
- Replying publicly here is the one thing to never do — even a 👍.
- Don't celebrate in-channel; congratulations to #success-stories are posted by `results-announcement`, not here.

## Verification
- Negative sentiment in a MONITOR_ONLY channel produces a Slack escalation and **zero** in-channel messages.
