---
name: ace-brand-discord-go-live
description: Verify and complete Discord go-live for an Ace brand profile after provisioning and setup.
version: 0.1.0
author: Hermes Agent
license: MIT
created_by: agent
---

# Ace brand Discord go-live

Use this when a brand profile already exists and the operator is connecting it to Discord for first launch.

## When to use
- Brand profile is provisioned and `setup` has been run.
- Operator needs help getting the Discord bot online on a VPS/CLI-only host.
- Gateway starts but Discord login or access-control behavior is unclear.

## Procedure
1. Verify the brand profile has:
   - `config.yaml`
   - `.env`
   - `SOUL.md`
   - `ace/knowledge.yaml`
2. Verify the brand `.env` contains at least:
   - `OPENROUTER_API_KEY`
   - `DISCORD_BOT_TOKEN`
   - `ACE_DATA_DIR`
3. Confirm `config.yaml` has the real `discord.guild_id` and final channel→behavior map.
4. For creator-facing/open server access:
   - leave Discord per-user allowlists empty during setup
   - set `GATEWAY_ALLOW_ALL_USERS=true` in the brand profile `.env`
5. In the Discord Developer Portal, enable Bot → Privileged Gateway Intents:
   - `Message Content Intent` is required for normal text replies
   - `Server Members Intent` is not needed unless using Discord user/role allowlists
6. Start the brand gateway with:
   - `hermes --profile <brand> gateway run`
7. If foreground run succeeds, optionally make it persistent:
   - `hermes --profile <brand> gateway install`
   - `hermes --profile <brand> gateway start`

## CLI/VPS guidance
- On headless VPS setups, use `hermes --profile <brand> config env-path` to find the profile `.env`.
- If you need to enable open access without an editor, append or update:
  - `GATEWAY_ALLOW_ALL_USERS=true`
- A home channel can be left unset during initial connection testing, but the first user message will trigger a "No home channel is set" notice. Set `DISCORD_HOME_CHANNEL` and `DISCORD_HOME_CHANNEL_NAME` in `.env` before going live — use the main support channel ID from `channel_directory.json`.

## Common pitfalls
- `PrivilegedIntentsRequired` on startup almost always means Message Content Intent is not enabled in the Discord developer portal.
- A blank Discord allowlist does not mean explicit open access if the gateway warns about unauthorized users being denied; set `GATEWAY_ALLOW_ALL_USERS=true` in the brand profile `.env`.
- Do not force Slack tokens into each brand profile if Slack is intentionally handled only by the root/operator profile.
- Discord channel names referenced by `knowledge.yaml` should match real configured channels, or onboarding answers will conflict with live server structure.
- **Bot connects but never replies** — this is almost always the `free_response_channels` gap. Even with correct `ace.discord.channels` behavior map and `ace.discord.scoping.free_response`, Hermes' gateway layer needs `discord.free_response_channels` populated with numeric channel IDs. See `ace-brand-discord-deployment` Phase 2 for the fix.
- Leaving the home channel unset triggers a noisy "No home channel is set" notice on the first message. Set `DISCORD_HOME_CHANNEL` + `DISCORD_HOME_CHANNEL_NAME` in `.env` before launch — use the main support channel ID from `channel_directory.json`.
- Setting `approvals.mode: 'off'` removes all terminal guards — the brand agent can read root `.env` via `cat`. Use `'smart'` for production brands unless the profile is strictly for development/testing.
- The `display.tool_progress` setting controls whether the agent shows skill-loading and tool-execution chatter in chat. Set to `'off'` for creator-facing brands — the chatter confuses non-technical users.
- Prompt-only rejection rules can still fail open if the toolset is too broad. When a brand bot keeps engaging with command/debug bait, shrink the public toolset before making the prompt longer.
- Remove `terminal` from public Discord toolsets unless a brand truly needs it. If the brand needs script execution, prefer a narrow allowlisted wrapper or a separate operator-only path.
- Treat file-safety read/write denials as defense-in-depth only — they are not the security boundary.
- When a brand agent over-explains why it rejected a request, the SOUL.md rejection rule is too weak. Keep SOUL.md short and flat: one exact rejection line for out-of-scope prompts, and no explanation. See `references/guardrails.md` for the launch lessons.
- If you need a compact reminder of the launch guardrail pattern, consult `references/guardrails.md`.

## Verification
- `hermes --profile <brand> profile show <brand>` shows `.env` exists.
- Brand gateway connects successfully to Discord with no privileged-intent error.
- The bot can answer in `ANSWER` / `FULL_ACTIVE` channels **without @mention**.
- The bot stays silent in `POST_ONLY`, `MONITOR_ONLY`, and `INACTIVE` channels.
- No tool-progress chatter, approval prompts, or home-channel warnings appear in Discord messages.
