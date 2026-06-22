---
name: creator-deal-lookup
description: Look up a specific creator's paid-collab/ambassador deal (terms, rate, schedule, deliverables, payment) from the profile store. Escalate if not found.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Creator Deal Lookup (grounding)

Personalized deal facts for paid-collab and ambassador channels. This is the deal-data equivalent
of `kb-search`: it grounds answers about *one* creator's terms, and a miss means escalate — never
invent terms, rates, or dates.

## When to Use
- In a paid-collab (1:1) channel or the ambassador channel, when a creator asks about their own
  deal: payment status/timing, deliverables due, schedule, deal terms.
- Pair with `kb-search` for general logistics; use this for creator-specific facts.

## Quick Reference
```
python ${HERMES_SKILL_DIR}/scripts/deal.py --handle "@creator"
```
Output: `{"found": true, "handle": "@creator", "terms": {...}}` or `{"found": false, ...}`.

## Procedure
1. Resolve the creator's handle from the channel/context.
2. Run the script.
3. If `found` → answer using **only** the returned `terms`.
4. If not `found` → acknowledge and `escalate-to-team` (reason `no_deal_on_file`).
5. Content-strategy, renegotiation, or complaint requests → always `escalate-to-team`, even when a deal exists.

## Pitfalls
- Never state a rate, deadline, or payment date that isn't in `terms`.
- Deal renegotiation is **not** a logistics answer — escalate it.
- Deals are brand-scoped to this profile.

## Verification
- A creator with a deal gets terms-grounded answers; an unknown creator triggers an escalation.
