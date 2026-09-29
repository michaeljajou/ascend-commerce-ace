---
name: setup-brand
description: Operator onboarding for a brand — write channel scoping + model config + SOUL.md, activate crons, and validate the brand knowledge file, inside an existing profile.
version: 0.3.0
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
   → Items 3–4 are scripted: once the bot is invited and its token is in the profile `.env`,
   `scripts/prep_server.py --profile-dir <profile_dir> --channels <brand channels>` creates
   the missing roles/channels idempotently, verifies the item-1 intents, audits the bot's
   own permissions (printing the fix-it re-invite URL — bots can't self-escalate), sets the
   bot's nickname, and sets the canonical Ace avatar (`--avatar-file
   <repo>/assets/ace-avatar.png`, or `--avatar-from-profile` to copy another bot's).
   Assigning **Ascend Team** to humans and the Vaulty toggle (item 6) stay manual.
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
8. *(Access gate)* The lock lives on the **@everyone base role** (View Channels off; creator/
   staff/bot roles carry their own View) — category overwrites alone don't reach unsynced
   child channels. Fail-closed for channels created later. To lock the server until
   onboarding is done — new members see ONLY the
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
- optional `features` object with boolean keys `general_qa`, `moderation`, `announcements`,
  `engagement`, and `reporting`. Omitted keys default to `true`, so existing specs keep the
  legacy behavior.

An onboarding-only profile disables every optional feature:
```
"features": {
  "general_qa": false,
  "moderation": false,
  "announcements": false,
  "engagement": false,
  "reporting": false
},
"onboarding": {"enabled": false}
```
Keep onboarding disabled until the profile is ready for live creator joins. Setting all five
feature values to false does not disable onboarding.

Supported combinations:
- `moderation`, `announcements`, `engagement`, and `reporting` can each be disabled on their
  own, in any mix, while `general_qa` stays enabled.
- `general_qa` can be disabled only in the onboarding-only profile above, with the other four
  disabled too. Setup rejects `general_qa: false` with any other feature enabled, including
  one left out of the spec, and writes nothing.
- While an onboarding-only profile has `onboarding.enabled: false`, its SOUL tells the agent to
  stay silent for every message. The onboarding and team-help redirect applies once
  onboarding is enabled.

## Brand knowledge
The brand's knowledge is a **`knowledge.yaml`** file the team maintains in the profile's data dir
(brief, FAQ, commission, samples, compliance, campaigns, …). It's read live by `get-knowledge` —
there is no ingest/embedding step.

For onboarding, setup reads only `onboarding.channels`, `onboarding.getting_started`, and
`onboarding.how_to_reach_team` from that file. It copies those values into
`ace.onboarding.guidance`. This bounded copy is the only knowledge available to an onboarding-only
agent after completion. Re-run setup after changing those onboarding sections. Other knowledge
edits still apply to `get-knowledge` on the next read when general Q&A is enabled. A profile with
general Q&A enabled gets the same copy but keeps its prior completion guidance, grounded in
samples and the live campaign; the copy changes nothing for it.

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
3. Activate only the cron jobs listed in the generated `cronjobs.yaml`. The effective feature map
   removes jobs for disabled functions. An onboarding-only profile contains only
   `onboarding-tick`. Do not register a missing job from a skill blueprint or another profile.
   When present, **sweep-unanswered** is the reply-gating half of the mention-only gateway. Register
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
   within the grace window, default 10 min, releases Ace from answering.)
3a. **Security hardening is applied automatically** by `setup.py` on every run: `approvals.mode: smart`, `approvals.cron_mode: approve`, `code_execution.mode: strict`, a `command_allowlist` scoped to this brand's own scripts, `session_reset: idle` (60 min), the brand's Discord toolset reduced to `code_execution` + `file` + `vision`, both background-review nudges off (`skills.creation_nudge_interval: 0`, `memory.nudge_interval: 0`), and every `display.*` chatter channel silenced so nothing operational leaks into Discord. Do not hand-edit these away without discussing with the operator — the next `setup-brand` re-run restores them.

   Two of these have bitten us and are worth knowing by name. `cron_mode` must never be
   `deny`: it blocks `execute_code` outright, and since every Ace skill runs a script, the
   agent keeps chatting while nothing is recorded. And `skills` must stay OUT of the Discord
   toolset: `skill_manage` is the sole trigger for Hermes' background self-improvement
   review, which once wrote a skill telling future sessions to skip the scripts and
   reconstruct creator data from memory. The bound skill is injected by the channel binding,
   so the agent needs no skill tool to read it.

   **Agent-authored skills are a bug, not an asset.** If `<profile>/skills/` contains a
   directory whose `SKILL.md` frontmatter has an `author` other than `Ascend Commerce`,
   delete it — it was written by a background review working around a broken script, and it
   encodes the workaround as doctrine.
3b. **First connect, then resolve channels.** Discord channel IDs don't exist until the bot connects once. Run `hermes --profile <brand_id> gateway run`, confirm "Channel directory built: N target(s)" with N > 0 in the logs, stop it, then run:
    ```
    python /opt/data/ascend-commerce-ace/skills/setup-brand/scripts/resolve_channels.py --profile-dir <profile_dir> --wire-onboarding
    ```
    (`--wire-onboarding` wires the onboarding channel while the brand is still paused —
    `ace.onboarding.enabled: false`. That flag is a LIVE switch: the fleet join listener
    connects as the brand's bot the moment it is true, so keep it false until go-live.)
    This wires five things (idempotent, safe to re-run):
    - **Mention-only gateway**: `discord.require_mention: true` with `discord.free_response_channels` cleared. Ace answers @mentions and DMs instantly and hears nothing else live — so team announcements can never draw an accidental reply. Creator messages the team doesn't answer within the grace window are handled by the `sweep-unanswered` cron instead (see step 3).
    - `DISCORD_HOME_CHANNEL` / `DISCORD_HOME_CHANNEL_NAME` in the profile `.env` — Ace's proactive-output channel, resolved from `discord.home_channel` in the spec (**default: `agent-ace`** — every brand server should have an `#agent-ace` ops channel; the script warns if it's missing).
    - The **Channel directory** block in `SOUL.md` — the live `#name → <#id>` map so Ace's channel mentions render as clickable links in Discord.
    - **Onboarding wiring** (only when `ace.onboarding.enabled` is true): creates the hidden-purpose `#onboarding` parent channel — or ADOPTS an existing one by name and applies the same door permissions to it, one overwrite at a time (a server that ran Vaulty already has an `onboarding` channel built for Vaulty's own role: no @everyone View, no bot entry) — (everyone can view, nobody posts at channel level; staff manage threads), stores `ace.onboarding.channel_id`, makes it the SOLE free-response channel (its private threads inherit it — that's what makes the onboarding conversation work without @mentions), and binds the `run-onboarding` skill to it. Prereqs: **Server Members privileged intent** ON in the Discord dev portal (the join poll needs it), bot has **Manage Roles + Manage Channels/Threads**, its role sits above the creator role, and Vaulty is OFF on that server.
    - **Cron delivery targets** in `cronjobs.yaml`: `discord:#<name>` → `discord:<id>`. Hermes
      resolves a name target by EXACT directory name, so a decorated channel (`📢│announcements`)
      misses and delivery dies on `int('#announcements')` while `cron list` still reports "ok".
      Register jobs from the resolved file; fix an already-registered one with
      `hermes --profile <brand> cron edit <job_id> --deliver discord:<id>`.
    Restart the gateway once more after this step.
4. Ensure the brand's **`knowledge.yaml`** is present in the data dir (`<profile>/ace`, = `ACE_DATA_DIR`),
   then validate it loads when general Q&A is enabled:
   ```
   python ${HERMES_SKILL_DIR}/../get-knowledge/scripts/get.py --section brand
   ```
   For a profile with general Q&A disabled, the command must return
   `{"disabled": "general_qa"}`. Re-run setup and inspect `ace.onboarding.guidance` in
   `config.yaml` instead. Setup refuses to activate restricted onboarding unless all three bounded
   guidance sections are present.
5. Verify (next section).

## Changing a live profile's feature policy
1. Pause the selected profile's gateway and cron jobs. Do not pause other profiles.
2. Edit the selected profile's saved spec, then re-run setup. This refreshes `config.yaml`,
   `ace/brand.json`, `SOUL.md`, copied scripts, and `cronjobs.yaml` from one resolved policy.
3. Inspect `hermes --profile <brand> cron list --all`. Pause or remove obsolete Ace jobs that are
   absent from the generated file. Create or edit only the jobs present in that file. Preserve
   unrelated jobs. The synthetic registered-job fixture and pure reconciliation test exercise
   this comparison without changing live scheduler state.
4. Restart the selected gateway and reset or refresh its existing sessions so cached support
   instructions cannot continue using a disabled feature.
5. Resume only the generated Ace jobs that should run for this profile.

To roll back, restore the previous feature values in the saved spec and repeat the same procedure.
Do not treat a manual edit to `config.yaml` or `ace/brand.json` as an active or complete rollout.

## Pitfalls
- The profile MUST exist first; this skill configures it, it doesn't create it.
- `MONITOR_ONLY` channels are read for sentiment but **never** replied to publicly — confirm the
  monitor wiring in the Phase 0 spike.
- Re-running is safe: config/SOUL/cron are overwritten from the spec.
- General knowledge edits apply on the next read. Changes to bounded onboarding guidance require a
  setup re-run.

## Verification
- `config.yaml` scoping lists match the intended channel map (free_response / ignored / monitor / post_targets).
- `SOUL.md` contains the brand voice and the never-fabricate + classify rules.
- `config.yaml` and `ace/brand.json` contain the same fully resolved feature map.
- `cronjobs.yaml` contains no job for a disabled feature; onboarding-only contains only
  `onboarding-tick`.
- When general Q&A is enabled, `get-knowledge` returns the `brand` section and a known FAQ phrase;
  an off-topic query returns empty. When it is disabled, the same support call returns the disabled
  result without reading the knowledge file.
