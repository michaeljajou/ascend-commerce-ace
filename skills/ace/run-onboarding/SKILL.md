---
name: run-onboarding
description: Onboard a new creator — collect TikTok handle + email, assign role, and give post-onboarding guidance. Replaces the Vaulty bot.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Run Onboarding (creator)

Welcomes a new creator, captures their details, assigns their role, and orients them. This is
creator-facing (distinct from `setup-brand`, which is operator-facing).

## When to Use
When a creator joins the server (Hermes member-join event) and in their onboarding channel/DM.

## Procedure
1. Start the record:
   ```
   python ${HERMES_SKILL_DIR}/scripts/onboarding.py start --handle "@creator"
   ```
2. Collect **TikTok username** and **email**, then save:
   ```
   python ${HERMES_SKILL_DIR}/scripts/onboarding.py set --handle "@creator" --tiktok "<tt>" --email "<email>"
   ```
3. Complete + assign role (Hermes role assignment), then mark active:
   ```
   python ${HERMES_SKILL_DIR}/scripts/onboarding.py complete --handle "@creator" --role creator
   ```
4. **Post-onboarding guidance** (in the brand voice): overview of key channels and what they're
   for; how to request samples / participate in campaigns; the current active campaigns/challenges
   they can join; how to reach the team or ask Ace; and an encouragement to introduce themselves
   in the community. Ground campaign specifics with `kb-search`.

## Pitfalls
- `complete` fails without **both** TikTok and email — keep collecting until you have them.
- Don't dump every channel; highlight the few that matter to a brand-new creator.
- Engagement nudges are handled separately by `nudge-inactive`; don't spam here.

## Verification
- The creator record reaches `onboarding_state = complete` with role + `last_active_at` set.
- The creator receives channel guidance and a current-campaign pointer grounded in the KB.
