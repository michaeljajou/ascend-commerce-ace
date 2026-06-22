---
name: moderate-message
description: Apply the 3-tier moderation escalation (Friendly → Formal → Final) for a detected category, recording history so repeats escalate.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Moderate Message

Carries out the moderation response for a category from `detect-sentiment`. Tier logic is computed
by the script (and recorded so repeat behavior escalates).

## When to Use
After `detect-sentiment` returns a non-`none` category.

## Procedure
1. Resolve + record the decision:
   ```
   python ${HERMES_SKILL_DIR}/scripts/moderate.py --handle "@creator" --category <category> --channel "<channel>"
   ```
   Returns `{tier, action, notify_team, redirect_thread, prior_count}`.
2. Execute the action:
   - **Friendly** (`empathize_offer_help`): respond empathetically; offer to help via DM or a
     private thread; optionally offer to flag the team.
   - **Formal** (`dm_guidelines_notify`): DM a community-guidelines reminder **and** notify the team in Slack.
   - **Final** (`timeout_delete_notify`): auto-timeout the user (configurable 1h/24h), delete the
     offending message, and notify the team immediately.
3. If `redirect_thread` is true (negativity in community-chat): move the conversation to a
   **private thread** so it doesn't sit in public — especially overnight.
4. If `notify_team` is true: post context to the brand Slack channel via `escalate-to-team`.
5. **Scams** come back as Final regardless of history: auto-delete the link/impersonation, warn the
   creator, and notify the team.

## Pitfalls
- Don't hand-pick the tier — the script computes it from recent history; trust it.
- Always record via the script (even Friendly) so the next incident escalates correctly.
- Deleting/timeouts are irreversible-ish — reserve for Final / scams, per the returned action.

## Verification
- Repeated issues by one creator climb Friendly → Formal → Final across calls.
- A scam is Final on the first hit and notifies the team.
