---
name: ace-brand-validation
description: Validate an Ace brand profile before Discord deployment — check channel scoping, knowledge-file consistency, and deploy-readiness.
version: 0.1.0
author: Hermes Agent
license: MIT
created_by: agent
---

# Ace Brand Validation

Validate a provisioned Ace brand profile before calling it deploy-ready. Use this after `create-brand` / `setup-brand`, after editing `knowledge.yaml`, or before connecting a brand to Discord.

## When to use
- A brand profile already exists and the operator wants to connect Discord.
- `knowledge.yaml` was added or edited and you need to catch contradictions.
- You need a concise deploy-readiness check for Ace brand config.

## What to verify
1. `config.yaml` has the real Discord `guild_id` and intended channel→behavior map.
2. The brand ACE data dir exists and contains `knowledge.yaml`.
3. Every channel named in `knowledge.yaml` is represented in the actual Discord config, unless it was intentionally removed from the content.
4. Operational guidance is internally consistent across sections:
   - `samples.how_to_request`
   - `onboarding.channels`
   - `onboarding.getting_started`
   - matching FAQ entries
5. High-risk contradictions are resolved before deploy, especially:
   - sample requests pointing to different channels in different sections
   - onboarding referencing channels absent from `config.yaml`
   - FAQ answers mentioning workflows that conflict with the structured sections

## Procedure
1. Read `config.yaml` from the brand profile.
2. Read `knowledge.yaml` from the brand ACE data dir.
3. Compare the Discord channel map against all channel mentions in onboarding, samples, campaigns, and FAQ entries.
4. Flag any placeholders still present (for example a fake `guild_id`).
5. Do not declare the brand ready until the config and knowledge content agree.

## Pitfalls
- A syntactically valid `knowledge.yaml` can still be operationally wrong if its channel names don't match the configured Discord map.
- The most common pre-deploy content bug is contradictory sample guidance, such as one section sending creators to `#our-products` while another says `#samples`.
- Missing channels in `config.yaml` lead to Ace giving instructions about places it cannot actually support.

## Verification
- `knowledge.yaml` exists at the ACE data dir path.
- `config.yaml` uses a real Discord `guild_id`, not a placeholder.
- Channel references in `knowledge.yaml` align with the configured Discord channel map.
- Sample-request instructions are consistent across `samples`, `onboarding`, and FAQ content.
- The operator has a short list of any remaining blockers: missing secrets, bot invite, or unresolved channel-map mismatches.
