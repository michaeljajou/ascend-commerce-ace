---
name: post-announcement
description: Announcement Type 4 — team-triggered ad-hoc announcement to a Discord channel, targeting one brand or all brands.
version: 0.1.0
author: Ascend Commerce
license: MIT
---

# Post Announcement (Announcement Type 4)

Ad-hoc announcements the team triggers on demand.

## When to Use
On an operator command, e.g. `/ace announce #channel <message>` (gated to operators via
`admin-commands`).

## Procedure
1. Parse the target channel and message from the command.
2. Post the message verbatim (lightly formatted to the brand voice if asked) to the target Discord
   channel in **this** brand's server.
3. **All-server broadcast:** when the operator targets all brands, post to the equivalent channel
   in every brand. Cross-profile fan-out is coordinated at the Hermes level (multiple profiles) —
   confirm the exact mechanism in the Phase 0 spike; default scope is the current brand only.

## Pitfalls
- Operator-only — never let a creator trigger an announcement.
- Don't alter the team's message meaning; ad-hoc posts are the team's words.
- Confirm the target channel exists before posting.

## Verification
- The message appears in the specified channel; an all-server broadcast reaches each brand's target channel.
