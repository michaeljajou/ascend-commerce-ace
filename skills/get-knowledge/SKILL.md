---
name: get-knowledge
description: Return the brand's knowledge (from its structured YAML file) for grounding. Returns the relevant subset, a named section, or all of it — empty if nothing matches.
version: 0.2.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Get Knowledge (grounding)

The brand's knowledge is a single structured **YAML file** in the profile (brief, FAQ, commission,
samples, compliance, campaigns, …) maintained by the team. This skill hands you the relevant slice
so you can answer accurately — and **never fabricate**.

## When to Use
- Inside `answer-from-kb`, before answering any logistics question.
- Any time you need a brand fact (commission, sample process, deadlines, policy, current campaign).

## Quick Reference
```
python ${HERMES_SKILL_DIR}/scripts/get.py --query "<the creator's question>"   # relevant subset
python ${HERMES_SKILL_DIR}/scripts/get.py --section commission                  # one section
python ${HERMES_SKILL_DIR}/scripts/get.py                                       # whole doc (small)
```

## Procedure
1. Run with the creator's question as `--query` (or pull a `--section` you know you need).
2. If output is **non-empty**: answer **using only** the returned YAML; state nothing beyond it.
3. If output is **empty**: do **not** answer from memory — hand off to `escalate-to-team`.

## Pitfalls
- For what's **currently running** (active campaign/challenge, deadline, prize), use
  `get-campaigns` instead — it reads the live campaign channels; this file's campaign
  entries may lag behind launches.
- Empty output is the **never-fabricate signal**, not an error → escalate.
- The knowledge doc is small; when in doubt, fetch the whole doc rather than guess a section name.
- Knowledge is brand-scoped to this profile — you can't see other brands'.
- Don't invent numbers/dates/policies absent from the YAML.

## Verification
- A question covered by the FAQ/sections returns matching YAML; an off-topic/unknown question returns empty.
