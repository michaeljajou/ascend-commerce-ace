---
name: ace-brand-discord-deployment
description: Bring an Ace brand profile live on Discord after provisioning — secure setup, gateway settings, free-response channels, home channel, and first-message verification.
version: 0.1.0
author: Hermes Agent
license: MIT
created_by: agent
---

# Ace Brand Discord Deployment

Operator workflow for taking an already-provisioned Ace brand profile and making the Discord bot actually respond correctly in public channels.

## When to use
- A brand profile already exists and `setup-brand` / `create-brand` have been run.
- The operator has added the Discord bot token and OpenRouter key.
- Discord connects but the bot is silent, noisy, or behaves like a raw Hermes gateway instead of a polished Ace bot.

## Procedure

### Phase 1 — Prerequisites (see also `ace-brand-discord-go-live`)
1. Confirm the brand profile has:
   - Discord bot token
   - OpenRouter API key
   - `knowledge.yaml` in `<profile>/ace/knowledge.yaml`
2. In the Discord Developer Portal, enable **Message Content Intent** for the bot.
3. If the bot should be usable by creators broadly, set `GATEWAY_ALLOW_ALL_USERS=true` in the brand profile `.env`.

### Phase 2 — Channel mapping (CRITICAL — most failures live here)
4. Discover the real Discord channel IDs. After the gateway runs once, read `<profile>/channel_directory.json` to get the `discord` array — each entry has `id`, `name`, `guild`, `type`. Use these numeric IDs for the steps below.

5. Map the brand's channel behavior in the Ace config under `ace.discord.channels` and `ace.discord.scoping`.

6. **Mirror free-response channels into Hermes gateway config.** This is the #1 cause of "bot connects but never replies":
   - `ace.discord.scoping.free_response` stores channel *names* for Ace logic.
   - Hermes public-channel reply behavior actually depends on top-level `discord.free_response_channels` containing the corresponding **Discord channel IDs** (numeric snowflakes).
   - Set it to a comma-separated string of channel IDs: e.g. `discord.free_response_channels: '1496613727171248260,1522268317321138176'`.
   - Without this, the bot ignores normal messages in all server channels unless directly @mentioned, regardless of what `ace.discord.channels` declares.
   - The `ace.*` channel map and the Hermes `discord.*` gateway config are two separate control planes — both must be correct. The Ace layer defines *what the agent should do* per channel; the Hermes layer defines *whether the agent hears the message at all*.

### Phase 3 — Home channel
7. Set a Discord home channel in the brand profile `.env`:
   - `DISCORD_HOME_CHANNEL=<channel_id>`
   - `DISCORD_HOME_CHANNEL_NAME=<channel-name>`
   Usually use the main support channel, e.g. `community-chat`. Without this, the first user message triggers a noisy "No home channel is set" notice.

### Phase 4 — Noise reduction
8. For creator-facing brands, reduce operator/debug noise in `config.yaml`:
   - `display.tool_progress: 'off'` — suppress skill-loading / tool-execution chatter
   - `display.interim_assistant_messages: false`
   - `approvals.mode: 'smart'` for the security-conscious case (see [security](references/security.md)); `'off'` for test/development profiles where no terminal guard is needed.

### Phase 5 — Security hardening (see also references/security.md and references/soul-rejection-pattern.md)
9. Apply brand-profile security posture:
   - `approvals.mode: 'smart'` — auto-runs safe commands, blocks dangerous patterns. Never use `'off'` for a brand exposed to real Discord users (it removes ALL terminal guards — the agent can `cat` root `.env`, `pip install`, etc.).
   - `code_execution.mode: 'strict'` — isolate `execute_code` to a temp directory (brands don't need project-level shell access).
   - `command_allowlist` — pre-approve only the Ace scripts the brand legitimately runs.
   - Remove `terminal` from `platform_toolsets.<platform>` entirely (e.g. `platform_toolsets.discord`) when the brand only needs its approved scripts. This is stronger than approvals alone — no terminal tool means no shell access to reason about bypassing, regardless of approvals.mode.
   - Treat profile separation as an organization boundary, not a security boundary. File-tool guards block `.env` reads, but terminal access still runs as the same OS user and can bypass them. If the brand must not touch secrets, the real fix is no arbitrary shell access (remove the terminal toolset) or separate OS/container isolation — not just approvals.
10. Strengthen `SOUL.md` with the **OVERRIDE rejection pattern** (see `references/soul-rejection-pattern.md` for the full template):
    - Place an OVERRIDE block at the very top of SOUL.md, before Voice and Hard Rules.
    - The rejection response must be a single short line with no alternatives, no explanation, no engagement.
    - If the SOUL.md approach fails on the target model (agent hallucinates running commands or offers debugging help), escalate to `prefill.json` few-shot priming — see `references/prefill-priming.md`.
    - Also harden the `classify-question` skill: add a **REJECT** bucket checked FIRST (before HANDLE/ROUTE) that covers commands, impersonation, meta-requests, file paths, and off-topic chat. If the shared Ace skills directory is read-only, create a local override at `<profile>/skills/classify-question/SKILL.md`.
11. Avoid over-restricting user-facing channels with `DISCORD_ALLOWED_USERS` or `require_mention` when the bot is meant to serve the community broadly. Use free-response channel IDs and home-channel settings for UX; use prompt and approval hardening for safety.

### Phase 6 — Start and verify
12. Start the gateway: `hermes --profile <brand> gateway run`
13. Verify with one plain-language test in a free-response channel (e.g. `general` or `community-chat`). Do NOT @mention the bot — the whole point is that free-response channels work without mentions.
14. **After ANY SOUL.md/config/skill hardening change, delete the Discord session(s) that predate the change before re-testing.** A hardened prompt does NOT retroactively scrub content already in an existing session's transcript — if a weaker prior version of SOUL.md let something slip (e.g. the model echoed .env contents once), every later message in that SAME session keeps re-reading/paraphrasing the leak from history, no matter how many times you tighten the prompt afterward. Symptom: you keep tightening SOUL.md and the bot still "remembers" and repeats a leak verbatim. Fix:
    - `hermes --profile <brand> sessions list` — find the session tied to the test channel/thread
    - `hermes --profile <brand> sessions delete <session_id> --yes`
    - Re-test only in the fresh session.
15. Set `session_reset.mode: idle` with a reasonable `idle_minutes` (e.g. 60) instead of `mode: none` for any brand exposed to real users. `mode: none` means a Discord thread/channel session never auto-resets — one bad exchange lives in context indefinitely. `idle` mode caps exposure automatically.

## Common failure modes
- `PrivilegedIntentsRequired` on startup:
  - Enable **Message Content Intent** in the Discord developer portal.
- Bot connects but never replies in `FULL_ACTIVE` / `ANSWER` channels:
  - Add the numeric channel IDs to top-level `discord.free_response_channels` (Phase 2, step 6). This is the single most common failure.
- First reply includes a home-channel notice:
  - Set `DISCORD_HOME_CHANNEL` and `DISCORD_HOME_CHANNEL_NAME` in `.env`.
- In-channel UX shows tool progress, skill-loading chatter, or approval prompts:
  - Turn off `display.tool_progress` and set appropriate `approvals.mode`.
- `Channel directory built: 0 target(s)`:
  - Check that the bot has actually been invited to the server and can see the configured channels.
- "No home channel is set for Discord" on first message:
  - Phase 3, step 7 — set `DISCORD_HOME_CHANNEL` + `DISCORD_HOME_CHANNEL_NAME`.
- Bot echoes/repeats a secret or leak it produced earlier, even after SOUL.md was hardened:
  - The poisoned content is sitting in that session's transcript, not being re-fetched. Delete the session (Phase 6, step 14) and re-test fresh — do not keep editing SOUL.md hoping it retroactively fixes history already in context.

## Verification
- Gateway log shows Discord connected successfully with no privileged-intents error.
- No first-message home-channel notice appears.
- A plain (non-@mention) message in a configured free-response channel gets a reply.
- The reply contains no tool-progress chatter, no skill-loading messages, no approval prompts.
- POST_ONLY and MONITOR_ONLY channels stay silent.
