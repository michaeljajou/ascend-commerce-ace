---
name: kb-search
description: Search the brand's knowledge base for grounded facts. Returns matching chunks, or empty if nothing is grounded.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# KB Search (grounding)

The one source of grounded brand facts. Call this whenever you need information from the brand's
knowledge base — it is how Ace stays accurate and **never fabricates**.

## When to Use
- Inside `answer-from-kb`, before answering any logistics question.
- Any time you are about to state a brand fact (commission, sample process, deadlines, policy).

## Quick Reference
```
python ${HERMES_SKILL_DIR}/scripts/search.py --query "<the creator's question>" --k 5
```
Output:
```json
{"results": [{"text": "...", "score": 0.71, "title": "Creator FAQ", "document_id": "...", "ord": 3}]}
```

## Procedure
1. Run the script with the creator's question as `--query`.
2. If `results` is **non-empty**: answer **using only** that text; cite nothing you didn't get back.
3. If `results` is **empty**: do **not** answer from memory — hand off to `escalate-to-team`.

## Pitfalls
- An empty `results` list is the **never-fabricate signal**, not an error. Treat it as "I don't know" → escalate.
- Do not lower `--min-score` to force a hit; a weak match is worse than an honest escalation.
- Results are brand-scoped to this profile — you cannot see other brands' knowledge.

## Verification
- A question answerable from the FAQ returns ≥1 result with a sensible `title`.
- An off-topic / unknown question returns `{"results": []}`.
