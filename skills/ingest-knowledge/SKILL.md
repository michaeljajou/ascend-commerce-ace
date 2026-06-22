---
name: ingest-knowledge
description: Ingest a brand's Google Drive knowledge folder into the profile's searchable store. Runs every 24h and on /ace update.
version: 0.1.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
    blueprint:
      schedule: "0 4 * * *"   # daily 04:00 — refresh while communities are quiet
      prompt: "Refresh this brand's knowledge base from its Google Drive folder using ingest-knowledge."
---

# Ingest Knowledge

Keeps the brand's searchable knowledge base in sync with its Google Drive folder. This is
**deterministic work, not reasoning** — just run the script; do not summarize or paraphrase docs
yourself.

## When to Use
- The 24h cron blueprint fires (automatic refresh).
- An operator runs `/ace update` (manual refresh after editing Drive).
- Right after `setup-brand` connects the Drive folder (first ingest).

## Quick Reference
```
python ${HERMES_SKILL_DIR}/scripts/ingest.py --source <DRIVE_FOLDER_ID>
# local dev / testing:
python ${HERMES_SKILL_DIR}/scripts/ingest.py --source ./fixtures/brand --kind local
```
The brand's Drive folder id comes from the profile config written by `setup-brand`.

## Procedure
1. Resolve the brand's Drive folder id from profile config.
2. Run `scripts/ingest.py --source <folder-id>`.
3. Report the returned summary (documents + chunks ingested) to the operator/log.

## Pitfalls
- Re-ingesting is **idempotent** per document (chunks are replaced, not duplicated) — safe to run often.
- If a document yields zero chunks it is skipped; an empty folder is a no-op, not an error.
- Never hand-edit the store; the Drive folder is the source of truth.

## Verification
- Summary shows `documents > 0` and `chunks > 0` for a non-empty folder.
- A follow-up `kb-search` for a known FAQ phrase returns a matching chunk.
