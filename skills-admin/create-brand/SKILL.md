---
name: create-brand
description: Operator-only — create a new brand's Hermes profile and register Ace's skills into it. Runs in the ROOT/admin profile only (brand profiles never get this skill). Use when an operator asks to onboard/add/create a new brand.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [terminal]
---

# Create Brand (operator / root profile only)

Provisions a **new brand** from the root/admin agent: creates the brand's Hermes profile and
registers Ace's per-brand skills into it — the same thing `ace brand create` does from the shell,
but driven from chat/Discord/Slack by the operator.

> This skill is installed **only in the root profile** (via `skills-admin/`). Client-facing brand
> profiles never receive it, so a brand agent can't create profiles or run this admin logic.

## When to use
- An operator asks to "create / add / onboard a new brand" (e.g. "create a brand called Glow Labs").

## What it does
Runs one command, which: `hermes profile create <name>` → registers `external_dirs` (the brand
skills) in the new profile's `config.yaml`. After this the new profile exists and sees all per-brand
skills (`setup-brand`, `get-knowledge`, …) — but **not** this admin skill.

## Procedure
1. Get the brand name from the operator (a short slug, e.g. `glow-labs`).
2. Run:
   ```
   ${HERMES_SKILL_DIR}/scripts/create-brand.sh "<name>"
   ```
3. Report the result, then tell the operator the next steps for that brand:
   - `<name> setup` — attach the brand's Discord/Slack tokens + OpenRouter key/model.
   - In the brand profile, run `/setup-brand` (channel scoping, crons, SOUL.md) and drop its
     `knowledge.yaml` into the brand's data dir (`ACE_DATA_DIR`, i.e. `<profile>/ace`).

## Pitfalls
- Operator-only by design — do not register this skill into brand profiles.
- The brand name becomes the profile slug; keep it short, lowercase, no spaces (use a hyphen).
- Re-running for an existing brand is safe: it skips creation and just re-registers the skills.

## Verification
- `<name> skills list` shows the per-brand skills (`setup-brand`, `get-knowledge`) as `local`.
