---
name: ace-brand-discord-setup
description: Collect and validate an Ace brand's Discord server/channel configuration interactively before secure token setup and deployment.
version: 0.1.0
author: Hermes Agent
license: MIT
created_by: agent
---

# Ace brand Discord setup

Collect the Discord-side configuration for an existing or newly provisioned Ace brand profile.

## When to use
- The operator wants to connect a brand to Discord.
- The brand profile exists but the Discord guild/channel map is incomplete or still uses placeholders.
- The operator needs guided help gathering server and channel details.

## Procedure
1. Confirm the brand/profile slug.
2. Ask for the Discord server ID (`guild_id`).
3. Collect channels interactively, one by one when the operator wants guidance:
   - ask for the exact channel name as shown in Discord
   - then ask for the behavior with a short explanation of the likely choices
4. Supported behaviors:
   - `POST_ONLY`: Ace posts announcements only
   - `POST_ANSWER`: Ace posts updates and answers logistics questions there
   - `ANSWER`: Ace answers direct logistics/product questions there
   - `FULL_ACTIVE`: Ace handles normal public Q&A there
   - `MONITOR_ONLY`: Ace reads sentiment there and never replies publicly
   - `PAID_COLLAB`: private paid-collab workflow channel
   - `AMBASSADOR`: ambassador-group workflow channel
   - `INACTIVE`: Ace ignores the channel
5. After collecting the map, verify that any channel names referenced in `knowledge.yaml` match the real Discord channels. Fix mismatches before deployment so onboarding/sample instructions do not contradict live routing.
6. Update the brand config with the real `guild_id`, `channels`, and scoping derived from the behaviors.
7. Tell the operator to run `<brand> setup` to attach secrets securely:
   - OpenRouter API key
   - Discord bot token
   - Slack token if escalations are used
8. Remind the operator to invite the bot to the server and test in an `ANSWER` or `FULL_ACTIVE` channel.

## Operator guidance pattern
- Be concise.
- If the operator asks for help, ask one question at a time.
- Include the minimal practical step to retrieve the value from Discord (for example, where to copy the server ID or how to read the channel name from the sidebar).
- Do not ask for secrets in chat.

## Verification
- `guild_id` is a real Discord server ID, not a placeholder.
- Every active channel has an explicit behavior.
- `knowledge.yaml` channel references match the configured Discord channel names.
- Secure setup and bot invite remain as the final operator-owned steps.
