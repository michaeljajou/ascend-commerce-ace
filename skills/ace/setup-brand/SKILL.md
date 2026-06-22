---
name: setup-brand
description: Operator onboarding for a brand — write channel scoping + model config + SOUL.md, activate crons, and run the first KB ingest inside an existing profile.
version: 0.1.0
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

## When to Use
- An operator runs `/ace setup-brand` for a new brand, or to re-apply config after editing the spec.

## Brand spec (collected interactively, or from a JSON/Drive config doc)
- `brand_id`, optional `brand_name`
- `discord.guild_id`, `discord.channels` → behavior map (POST_ONLY / POST_ANSWER / ANSWER /
  FULL_ACTIVE / MONITOR_ONLY / PAID_COLLAB / AMBASSADOR / INACTIVE)
- `slack_channel`, `drive_folder`, optional `growi_project`
- `model` (answer model), optional `classify_model`, `embed_model`, `voice`, `brand_name`

## Procedure
1. Gather the spec (ask the operator, or read a config doc from the brand's Drive folder).
2. Write the profile artifacts:
   ```
   python ${HERMES_SKILL_DIR}/scripts/setup.py --spec <spec.json>
   ```
   This writes `config.yaml` (channel scoping + model), `SOUL.md` (voice + locked rules),
   `cronjobs.yaml` (recurring jobs targeted at this brand's channels).
3. Activate the cron jobs (accept blueprint suggestions or register from `cronjobs.yaml`).
4. Run the **first KB ingest**:
   ```
   python ${HERMES_SKILL_DIR}/../ingest-knowledge/scripts/ingest.py --source <drive_folder>
   ```
5. Verify (next section).

## Pitfalls
- The profile MUST exist first; this skill configures it, it doesn't create it.
- `MONITOR_ONLY` channels are read for sentiment but **never** replied to publicly — confirm the
  monitor wiring in the Phase 0 spike.
- Re-running is safe: config/SOUL/cron are overwritten from the spec; ingest is idempotent.

## Verification
- `config.yaml` scoping lists match the intended channel map (free_response / ignored / monitor / post_targets).
- `SOUL.md` contains the brand voice and the never-fabricate + classify rules.
- First ingest reports `documents > 0`; a `kb-search` for a known FAQ phrase returns a hit.
