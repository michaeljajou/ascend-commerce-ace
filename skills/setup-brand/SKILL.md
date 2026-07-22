---
name: setup-brand
description: Operator onboarding for a brand — write channel scoping + model config + SOUL.md, activate crons, and validate the brand knowledge file, inside an existing profile.
version: 0.2.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Setup Brand (operator onboarding)

Configures Ace for one brand **inside its already-created Hermes profile**. This is operator-facing
(adding a brand), distinct from `run-onboarding` (welcoming a creator).

> Prerequisite: the profile already exists and has its Discord bot token, Slack token, and
> OpenRouter key attached (a thin Hermes-CLI step). This skill does **not** create the profile.

## Discord & Slack checklist — run this for EVERY new brand

Walk it top to bottom with the brand operator; each item has bitten us at least once. Items
marked *(portal)* live in the Discord **Developer Portal**; *(server)* items live in the brand's
**Server Settings** — portal toggles do NOT grant server permissions.

1. *(portal)* Bot → Privileged Gateway Intents: **Message Content Intent** ON (required for the
   bot to read messages at all) and **Server Members Intent** ON (required by the onboarding
   join poll and role lookups).
2. *(server)* Invite the bot; then edit the **bot's role**: enable **Manage Roles**,
   **Manage Channels**, and **Manage Threads** (needed to create #onboarding, open private
   threads, and assign creator roles).
3. *(server)* Create the roles: **Ascend Team** (assign to every team member — it gates the
   reply-sweep, onboarding staff visibility, and never-onboard filtering), plus **onboarded**
   and **creator** (what completion assigns). Drag both creator roles **below the bot's role**
   — Discord forbids assigning roles at or above the assigner's own.
4. *(server)* Create the **#agent-ace** channel (Ace's home for cron output/notifications;
   resolve_channels wires it automatically).
5. *(Slack)* Invite the workspace's Hermes bot to **#ace-escalations** (`/invite @<bot>`), and
   copy the bot token into the brand profile's `.env` **as `ACE_SLACK_BOT_TOKEN`** (never
   `SLACK_APP_TOKEN`, and not under the name `SLACK_BOT_TOKEN` — that name makes the brand's
   gateway try to run a Slack platform and retry-connect forever; brands are outbound-only).
6. **Before enabling onboarding** (`ace.onboarding.enabled`): turn **Vaulty's join handling
   OFF** on that server — running both risks duplicate onboarding spaces and role conflicts.
7. *(Slack)* Create **#ace-onboarding** and invite the bot (`/invite @<bot>`). Every
   completed onboarding posts the creator's captured details there, brand-tagged. Kept
   separate from #ace-escalations so signups stay scannable. Override per brand with
   `onboarding.data_channel`. *(Optional extra: a Google Sheet mirror — paste the `doPost`
   snippet from `_lib/sheet.py` into Apps Script, deploy as a Web app with access
   "Anyone", and set `onboarding.sheet_webhook` to the deployment URL.)*
8. *(Access gate)* To lock the server until onboarding is done — new members see ONLY the
   onboarding channel — run after step 3b:
   ```
   python /opt/data/ascend-commerce-ace/skills/setup-brand/scripts/gate_channels.py --profile-dir <profile_dir>          # dry run
   python /opt/data/ascend-commerce-ace/skills/setup-brand/scripts/gate_channels.py --profile-dir <profile_dir> --apply
   ```
   It denies @everyone View Channel on every public channel and grants it to the
   `onboarded`/`creator` roles (staff keeps access; the onboarding channel stays visible —
   it's the only door in). `--apply --open` reverses it. Run it again after adding channels.
9. After any of the above changes: re-run step 3b (resolve_channels) + restart the gateway.

Verify items 1–3 without clicking around: `assign_role.py` and the tick scripts print precise
errors, and a members-list API call failing with `Missing Access` means the intent (1) is off.

## When to Use
- An operator runs `/ace setup-brand` for a new brand, or to re-apply config after editing the spec.

## Brand spec (collected interactively, or from a JSON/YAML config)
- `brand_id`, optional `brand_name`
- `discord.guild_id`, `discord.channels` → behavior map (POST_ONLY / POST_ANSWER / ANSWER /
  FULL_ACTIVE / MONITOR_ONLY / PAID_COLLAB / AMBASSADOR / INACTIVE)
- `slack_channel`, optional `growi_project`
- `model` (answer model), optional `classify_model`, `voice`, `brand_name`

## Brand knowledge
The brand's knowledge is a **`knowledge.yaml`** file the team maintains in the profile's data dir
(brief, FAQ, commission, samples, compliance, campaigns, …). It's read live by `get-knowledge` —
there is no ingest/embedding step.

## Procedure
1. Gather the spec (ask the operator, or read a config file).
2. Write the profile artifacts:
   ```
   python ${HERMES_SKILL_DIR}/scripts/setup.py --spec <spec.json>
   ```
   This writes `config.yaml` (channel scoping + model + knowledge_file pointer), `SOUL.md`
   (voice + locked rules), `cronjobs.yaml` (recurring jobs targeted at this brand's channels), and
   merges **`ACE_DATA_DIR=<profile>/ace`** into the profile `.env`. That env var is the bundle's
   orchestrator-agnostic data-dir contract — `store.py` and `get-knowledge` read only `ACE_DATA_DIR`;
   this skill is the one place that maps Hermes' profile path onto it.
3. Activate the cron jobs (accept blueprint suggestions or register from `cronjobs.yaml`).
   The **sweep-unanswered** job is the reply-gating half of the mention-only gateway — register
   it with its zero-token pre-script (the script gates the agent; a tick with nothing to do
   never touches the LLM):
   ```
   hermes --profile <brand_id> cron create "every 2m" --name sweep-unanswered \
     --skill sweep-unanswered --script ace-sweep.py --deliver discord \
     "Handle the unanswered creator messages surfaced above, following the sweep-unanswered skill exactly. End with only [SILENT]."
   ```
   (`ace-sweep.py` is installed into `<profile>/scripts/` by `setup.py`. Team members are
   identified by the **"Ascend Team"** Discord role — the default in every brand; override
   with `discord.team_role` in the spec. Role-holders are never swept, and their reply
   within the grace window, default 5 min, releases Ace from answering.)
3a. **Security hardening is applied automatically** by `setup.py` on every run: `approvals.mode: smart`, `code_execution.mode: strict`, a `command_allowlist` scoped to this brand's own scripts, `session_reset: idle` (60 min), the `terminal` tool stripped from the brand's `discord`/`cli` platform toolsets, and `display.tool_progress: off` / `interim_assistant_messages: false` so no tool chatter leaks into Discord. Do not hand-edit these away without discussing with the operator — the next `setup-brand` re-run restores them.
3b. **First connect, then resolve channels.** Discord channel IDs don't exist until the bot connects once. Run `hermes --profile <brand_id> gateway run`, confirm "Channel directory built: N target(s)" with N > 0 in the logs, stop it, then run:
    ```
    python /opt/data/ascend-commerce-ace/skills/setup-brand/scripts/resolve_channels.py --profile-dir <profile_dir>
    ```
    This wires four things (idempotent, safe to re-run):
    - **Mention-only gateway**: `discord.require_mention: true` with `discord.free_response_channels` cleared. Ace answers @mentions and DMs instantly and hears nothing else live — so team announcements can never draw an accidental reply. Creator messages the team doesn't answer within the grace window are handled by the `sweep-unanswered` cron instead (see step 3).
    - `DISCORD_HOME_CHANNEL` / `DISCORD_HOME_CHANNEL_NAME` in the profile `.env` — Ace's proactive-output channel, resolved from `discord.home_channel` in the spec (**default: `agent-ace`** — every brand server should have an `#agent-ace` ops channel; the script warns if it's missing).
    - The **Channel directory** block in `SOUL.md` — the live `#name → <#id>` map so Ace's channel mentions render as clickable links in Discord.
    - **Onboarding wiring** (only when `ace.onboarding.enabled` is true): creates the hidden-purpose `#onboarding` parent channel (everyone can view, nobody posts at channel level; staff manage threads), stores `ace.onboarding.channel_id`, makes it the SOLE free-response channel (its private threads inherit it — that's what makes the onboarding conversation work without @mentions), and binds the `run-onboarding` skill to it. Prereqs: **Server Members privileged intent** ON in the Discord dev portal (the join poll needs it), bot has **Manage Roles + Manage Channels/Threads**, its role sits above the creator role, and Vaulty is OFF on that server.
    Restart the gateway once more after this step.
4. Ensure the brand's **`knowledge.yaml`** is present in the data dir (`<profile>/ace`, = `ACE_DATA_DIR`),
   then validate it loads:
   ```
   python ${HERMES_SKILL_DIR}/../get-knowledge/scripts/get.py --section brand
   ```
5. Verify (next section).

## Pitfalls
- The profile MUST exist first; this skill configures it, it doesn't create it.
- `MONITOR_ONLY` channels are read for sentiment but **never** replied to publicly — confirm the
  monitor wiring in the Phase 0 spike.
- Re-running is safe: config/SOUL/cron are overwritten from the spec.
- Knowledge is just a YAML file edited in the profile — no refresh/ingest needed; edits apply on next read.

## Verification
- `config.yaml` scoping lists match the intended channel map (free_response / ignored / monitor / post_targets).
- `SOUL.md` contains the brand voice and the never-fabricate + classify rules.
- `get-knowledge` returns the `brand` section and a known FAQ phrase; an off-topic query returns empty.
