---
name: create-brand
description: Operator-only — create and provision a new brand from the root/admin agent. Gathers the brand's config conversationally (asking for anything missing), then creates the Hermes profile, registers Ace's skills, and writes the brand config. Runs in the ROOT profile only. Use when an operator asks to onboard/add/create a new brand.
version: 0.2.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [terminal]
---

# Create Brand (operator console — root profile only)

Provision a new brand by **talking to the root agent**: the operator gives whatever details they
have, you ask for anything missing, then you create + register + configure the brand's profile in one
step. This is the conversational front end over `create-brand.sh` (which wraps `install.sh` +
`setup-brand`).

> Installed **only in the root profile** (via `skills-admin/`). Brand profiles never receive this
> skill, so a brand agent can't create or configure other brands.

## When to use
- An operator says "create / add / onboard a new brand" (with or without full details).

## Two things this does NOT handle (tell the operator)
- **Secrets** (OpenRouter key, Discord/Slack tokens) — those go through Hermes' secure prompt:
  `<brand> setup`. Never put secrets in the spec.
- **Knowledge** (`knowledge.yaml`) — the brand team maintains it as a living file; it's dropped into
  the brand's data dir (`ACE_DATA_DIR` = `<profile>/ace`) after provisioning, not part of this step.

## Brand config to collect (ask only for missing REQUIRED fields)
Required — ask if missing:
- `brand_id` — short lowercase slug, also the profile name (e.g. `glow-labs`).
- `discord.guild_id` and `discord.channels` — a map of channel name → behavior, where behavior is one of:
  - `POST_ONLY` (announcements: cron posts, no replies)
  - `POST_ANSWER` (campaigns/challenges: cron posts + answers logistics)
  - `ANSWER` (e.g. our-products: answers from knowledge)
  - `FULL_ACTIVE` (community-chat: primary Q&A + sentiment)
  - `MONITOR_ONLY` (success-stories: read for sentiment, never reply publicly)
  - `PAID_COLLAB` (private 1:1 collab channels)
  - `AMBASSADOR` (ambassador group channel)
  - `INACTIVE` (content-inspo, coaching: ignored)

Optional — use if given, otherwise **omit from the spec** (a default applies; do NOT ask or invent):
- `model` — answer model (OpenRouter id, e.g. `anthropic/claude-sonnet-4-6`). Omit → the brand
  inherits Hermes' default model.
- `slack_channel` — escalation channel (e.g. `#glow-ops`). Omit → the configured default channel.
- `brand_name`, `voice` (brand tone), `classify_model`, `growi_project`.

## Procedure
1. Collect the fields above from the operator; **ask follow-up questions only for missing REQUIRED
   fields** (brand_id, discord guild + channels). **Never ask for or invent optional fields** like
   `model` or `slack_channel` — if the operator didn't give them, omit them from the spec and the
   defaults apply. Confirm the channel→behavior map explicitly.
2. Write the gathered config to a temporary JSON spec, e.g. `/tmp/<brand_id>.json`:
   ```json
   {
     "brand_id": "glow-labs",
     "brand_name": "Glow Labs",
     "model": "anthropic/claude-sonnet-4-6",
     "voice": "Friendly, upbeat, concise.",
     "slack_channel": "#glow-ops",
     "discord": {
       "guild_id": "123456789",
       "channels": {
         "announcements": "POST_ONLY",
         "community-chat": "FULL_ACTIVE",
         "campaigns": "POST_ANSWER",
         "success-stories": "MONITOR_ONLY",
         "our-products": "ANSWER",
         "content-inspo": "INACTIVE"
       }
     }
   }
   ```
3. Provision in one command:
   ```
   ${HERMES_SKILL_DIR}/scripts/create-brand.sh "<brand_id>" --spec /tmp/<brand_id>.json
   ```
   This creates the profile, registers the brand skills, and writes `config.yaml`, `SOUL.md`,
   `cronjobs.yaml`, and `ACE_DATA_DIR` into the profile.
4. Report success and the remaining operator steps:
   - `<brand_id> setup` — attach the OpenRouter key + Discord/Slack tokens (secure).
   - Drop the brand's `knowledge.yaml` into the data dir (`<profile>/ace`); the brand team keeps it
     current thereafter.

## Pitfalls
- Operator-only; never register into brand profiles.
- `brand_id` must be a clean slug (lowercase, hyphens, no spaces) — it's the profile name.
- Secrets never go in the spec — only via `<brand> setup`.
- Re-running for an existing brand is safe: it skips creation and re-applies config (idempotent).

## Verification
- `<brand_id> skills list` shows the per-brand skills as `local`.
- The profile has `config.yaml`, `SOUL.md`, `cronjobs.yaml`, and `.env` with `ACE_DATA_DIR`.
