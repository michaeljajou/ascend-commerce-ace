---
name: escalate-to-team
description: Hand a question or issue to the brand's Slack channel with full context, and log it for KB improvement.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Escalate To Team

Route anything Ace shouldn't answer to the brand's Slack channel — without leaving the creator
hanging. Used for: not-grounded logistics questions, creative-strategist requests, deal
renegotiation, and escalated complaints.

## When to Use
- `answer-from-kb` found nothing grounded (`not_grounded`).
- `classify-question` returned ROUTE (`creative-strategist`).
- A creator asks to renegotiate a deal or raises a complaint Ace can't resolve.

## Procedure
1. **Acknowledge the creator** in-channel: tell them you're flagging it to the team — never go silent.
2. **Post to the brand Slack channel** (via Hermes' Slack delivery) with:
   - Which Discord channel it came from
   - Creator name / handle
   - The question or issue
   - The last 3 messages for context
   - What Ace replied (if anything)
   - What's needed from the team
3. **Log it** for KB improvement:
   ```
   python ${HERMES_SKILL_DIR}/../_lib/log_cli.py interaction --status escalated \
     --channel "<channel>" --handle "<creator>" --question "<q>"
   ```
   (Use `--status routed` instead when the reason is `creative-strategist`.)

## Pitfalls
- Always acknowledge the creator first; an escalation the creator can't see feels like being ignored.
- Don't dump raw logs into Slack — give the team a tight, skimmable summary + the action needed.
- Don't attempt the answer "anyway" after deciding to escalate.

## Verification
- The creator receives a polite acknowledgment.
- The Slack post contains all six context fields and a clear "needed from team".
- An `escalated` (or `routed`) interaction is recorded in the store.
