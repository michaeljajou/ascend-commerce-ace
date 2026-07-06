---
name: ace-discord-channel-mapping
description: Guided operator workflow for collecting and confirming Discord channel-to-behavior mappings when provisioning or reconfiguring an Ace brand.
version: 0.1.0
author: Hermes Agent
license: MIT
created_by: agent
---

# Ace Discord Channel Mapping

Collect a brand's Discord server/channel configuration for Ace in a way that is easy for a human operator to answer correctly.

## When to use
- Creating a new Ace brand with `create-brand`.
- Reconfiguring an existing brand's Discord scope.
- Any time the operator knows the server/channel layout but not Ace's internal behavior labels.

## Principle
Operators often know the channel names but not the behavior taxonomy. Do not dump the full config request at once if the operator wants guidance. Gather the mapping in a guided sequence.

## Recommended workflow
1. Ask for the Discord server ID.
2. Ask for the exact current channel names in one pass.
3. Walk the channels **one by one**.
4. For each channel, offer only the most relevant behavior choices with a short plain-English explanation.
5. Confirm the selected mapping before moving to the next channel.
6. After all channels are mapped, restate the full channel→behavior map for confirmation before writing config.

## Behavior explanations to use
- `POST_ONLY` — Ace posts scheduled updates there and does not answer publicly.
- `POST_ANSWER` — Ace posts updates there and also answers logistics questions.
- `ANSWER` — Ace answers direct logistics/product questions there.
- `FULL_ACTIVE` — Ace is fully active for public Q&A there.
- `MONITOR_ONLY` — Ace reads sentiment/signals there but never replies publicly.
- `PAID_COLLAB` — private paid-collab creator channel.
- `AMBASSADOR` — ambassador program group channel.
- `INACTIVE` — Ace ignores the channel.

## Operator UX rules
- If the operator asks to be guided step by step, do exactly that.
- Keep each question short.
- Do not ask about optional fields during the mapping pass.
- Use the operator's literal channel names; do not rename them.
- If the knowledge file references channels not yet mapped, flag the mismatch and resolve it before deployment.

## Pitfalls
- Do not assume `#general` means `FULL_ACTIVE`; confirm it.
- Do not leave placeholder guild IDs in config.
- Do not deploy with channels mentioned in `knowledge.yaml` but missing from Discord scoping.
- Do not mix sample-request instructions across `#samples` and `#our-products` without reconciling them.

## Verification
- Guild ID is real, not a placeholder.
- Every channel Ace should touch has an explicit behavior.
- Any channel named in `knowledge.yaml` is either mapped intentionally or the knowledge file is updated.
- Final config restatement matches the operator's confirmed answers.
