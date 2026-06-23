---
name: setup-brand
description: Operator onboarding for a brand — write channel scoping + model config + SOUL.md, activate crons, and validate the brand knowledge file, inside an existing profile.
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
