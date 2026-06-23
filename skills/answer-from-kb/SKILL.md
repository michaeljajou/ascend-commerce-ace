---
name: answer-from-kb
description: Answer a shop-operator (logistics) question using ONLY grounded knowledge-base results. Never fabricate; escalate if not grounded.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Answer From KB

Answer logistics questions **grounded in the brand's knowledge base** — and only when grounded.
This is where the never-fabricate rule is enforced at the point of answering.

## When to Use
After `classify-question` returns **HANDLE**.

## Procedure
1. Call `get-knowledge`:
   ```
   python ${HERMES_SKILL_DIR}/../get-knowledge/scripts/get.py --query "<the question>"
   ```
2. **If it returns knowledge (non-empty):** write a concise, friendly answer in the brand voice
   using **only** facts present in the returned YAML. Do not add details that aren't there.
3. **If it returns nothing (empty):** do **not** answer from memory or general knowledge. Acknowledge
   the question and hand off to `escalate-to-team` (reason `not_grounded`).
4. Log the outcome:
   ```
   python ${HERMES_SKILL_DIR}/../_lib/log_cli.py interaction --status answered \
     --channel "<channel>" --handle "<creator>" --question "<q>" --answer "<a>"
   ```
   Capture the printed `interaction_id` so `record-feedback` can attach 👍/👎.

## Pitfalls
- If the knowledge only partially covers the question, answer the covered part and **escalate the
  rest** — do not fill gaps with assumptions.
- Never state numbers (rates, dates, timelines) that aren't in the returned knowledge.
- Keep it short; link the creator to the next step rather than dumping the whole doc.

## Verification
- A KB-answerable question yields an answer whose every fact appears in the returned knowledge.
- An unanswerable question produces an escalation, not a guess.
