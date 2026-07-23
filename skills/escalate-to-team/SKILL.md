---
name: escalate-to-team
description: Hand a question or issue to the brand's Slack channel with full context, and log it for KB improvement.
version: 0.2.1
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
1. **Acknowledge the creator** in-channel: tell them you're flagging it to the team — never go
   silent. (Exception: when invoked by `sweep-unanswered` for a creative-strategist question,
   skip the acknowledgment — the strategist replies in-channel themselves.)
2. **Post to the team Slack channel** — all brands share it, and the script automatically
   prefixes your message with this brand's tag (`[<brand>]`), so just write the summary:
   ```
   python ${HERMES_SKILL_DIR}/../_lib/slack_cli.py post --text "<summary>"
   ```
   Write plain text with simple bullets. The script translates formatting for Slack itself
   (`**bold**`, `### headers`, and Discord `<#id>` channel tags all come out right) — never
   hand-write Slack syntax.
   The summary must contain:
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
- The creator receives a polite acknowledgment (except in sweep mode for creative questions).
- The Slack post starts with the `[<brand>]` tag and contains all six context fields and a
  clear "needed from team".
- An `escalated` (or `routed`) interaction is recorded in the store.
