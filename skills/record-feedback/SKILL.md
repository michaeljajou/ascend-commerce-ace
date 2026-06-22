---
name: record-feedback
description: Record a creator's 👍/👎 reaction on an Ace answer for quality tracking.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Record Feedback

Capture thumbs-up / thumbs-down reactions on Ace's answers so we can track answer quality and
surface weak spots for KB improvement.

## When to Use
When a creator reacts 👍 or 👎 to a message Ace posted that has a known `interaction_id`
(returned by `answer-from-kb` when it logged the answer).

## Procedure
```
python ${HERMES_SKILL_DIR}/../_lib/log_cli.py feedback --interaction-id <id> --value up    # or: down
```

## Pitfalls
- Only record feedback for messages Ace authored and logged; ignore reactions on other messages.
- One reaction = one record; if a creator changes their reaction, record the new value (latest wins in reporting).

## Verification
- After a 👍/👎, a `feedback` row exists linked to the interaction, and it shows up in the daily digest's thumbs-up %.
