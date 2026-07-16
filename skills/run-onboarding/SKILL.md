---
name: run-onboarding
description: Onboard a new creator in their private thread — collect TikTok handle + email with retry limits, assign their role (never fail silently), deliver the guidance sequence, and send 48h nudges. Replaces the Vaulty bot.
version: 0.2.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Run Onboarding (creator)

Takes a creator from "just joined" to "actively participating" with zero manual work. The
zero-token cron tick (`ace-onboarding-tick.py`) detects joins, creates the private thread, and
posts the welcome + username ask — **you** take over from the creator's first reply.

**Master switch:** if `ace.onboarding.enabled` is false in the profile config, do nothing —
tell whoever asked that onboarding is currently disabled.

## When to Use
- **Conversation mode:** any creator message in their private onboarding thread (this skill is
  bound to the onboarding channel; threads inherit it).
- **Nudge mode:** the cron tick woke you with `onboarding_nudges_due`.

## Conversation mode

**The creator's handle comes from the THREAD NAME, nothing else**: the thread is named
`welcome-<username>`, so thread `welcome-jane77` → handle `@jane77`. Never use their display
name — display names don't match the store record and create phantom rows.

Check where they are first: `python ${HERMES_SKILL_DIR}/scripts/onboarding.py status --handle "@<username>"`
(if there's no record yet, `start` one). Then continue from the first missing piece:

1. **TikTok username.** Valid: a plausible TikTok handle (1–24 chars; letters, digits, `_`, `.`;
   with or without a leading @; also accept a tiktok.com profile URL and extract the handle).
   Invalid (blank, "idk", an email, obvious junk) → count it and re-ask with a clarifying prompt:
   ```
   python ${HERMES_SKILL_DIR}/scripts/onboarding.py retry --handle "@<username>"
   ```
   When `retries` reaches `ace.onboarding.max_retries` (default 3): STOP looping — flag it
   (`onboarding.py flag`), post to the team Slack via `_lib/slack_cli.py` (who, which field,
   what they said), and tell the creator warmly that a team member will take it from here.
   Valid → save: `onboarding.py set --handle "@<username>" --tiktok "<handle>"`
2. **Email.** Same retry-then-flag logic. Valid = normal email shape.
   Valid → save: `onboarding.py set --handle "@<username>" --email "<email>"`
3. **Role assignment** (both fields collected). `assign_role.py` assigns every role in
   `ace.onboarding.creator_roles` (default: `onboarded` + `creator` — Vaulty parity):
   ```
   python ${HERMES_SKILL_DIR}/scripts/assign_role.py --user-id <discord_id>
   python ${HERMES_SKILL_DIR}/scripts/onboarding.py complete --handle "@<username>" --role creator
   ```
   If `assign_role.py` exits non-zero: **never fail silently** — this blocks their channel
   access. Tell the creator the team's been looped in to finish their access, AND post the
   script's error to Slack (`slack_cli.py`) immediately. Do not mark complete.
4. **Guidance sequence** — one friendly message (or two short ones), in the brand voice, covering
   in order:
   1. What the key channels are for (use clickable `<#id>` tags from the SOUL Channel directory;
      just the few that matter to someone brand new).
   2. How to request samples / join campaigns — ground in `get-knowledge` (samples section).
   3. **What's actually running right now** — ground in `get-campaigns` (never boilerplate).
   4. How to get help: ask Ace in the community channel, or the team for anything creative.
   5. A nudge to introduce themselves in the community channel.
   Then stamp it — the 48h clock starts here:
   ```
   python ${HERMES_SKILL_DIR}/scripts/onboarding.py guided --handle "@<username>"
   ```

## Nudge mode (woken by the tick with `onboarding_nudges_due`)

For each entry: write ONE friendly, low-pressure line in the brand voice pointing at a single
concrete next step. Pick it by `stage`:
- `stage: collecting` — they never replied to the welcome: point them back to their setup
  thread (`<#thread_id>`), e.g. "your 1-minute setup is waiting whenever you're ready".
- `stage: guided` — they finished setup but went quiet: prefer the live campaign/challenge
  (`get-campaigns`), else "come say hi" in the community channel.
No guilt-tripping. Deliver per `nudge_via`:
- `dm` (default): `python ${HERMES_SKILL_DIR}/scripts/send_dm.py --user-id <discord_id> --text "<nudge>"`
  — if the DM fails (user blocks server DMs), fall back to posting in their `thread_id` via
  `${HERMES_SKILL_DIR}/../sweep-unanswered/scripts/reply.py --channel-id <thread_id>`.
- `space`: post in their `thread_id` directly.
End your turn with only `[SILENT]`.

## Pitfalls
- **NEVER create cron jobs from an onboarding conversation** — no "check later" jobs, no
  running scripts via cron as a workaround. Cron deliveries leak into the creator's thread
  as raw "Cronjob Response" spam. If a script fails, run it once more; if it still fails,
  post the exact error to Slack (`_lib/slack_cli.py`), tell the creator the team will finish
  their setup, and END the turn. A short clean failure beats a long improvised one.
- Keep turns short — one question or one step per message. No status chatter, no walls of text.
- The tick already marked them nudged when it woke you — deliver every nudge you were handed;
  if delivery fails both ways, post the failure to Slack instead of dropping it.
- `complete` fails without BOTH TikTok and email — that's the guard, not an error to work around.
- Retries are per-creator and cumulative across both fields — the limit is a total patience
  budget, not per-field.
- Never re-run the full flow for someone whose `status` is already `guided`/`active` — answer
  whatever they asked instead (a duplicate join resumes, never restarts).
- **Rejoins restart automatically**: anyone who left the server and comes back gets a fresh
  thread + welcome-back from the tick, with timers reset but their TikTok/email remembered —
  if `status` shows those already set, skip straight to role assignment and guidance.
- Escalations (7-day quiet) are the tick's job, not yours — don't nudge anyone twice.
- Don't dump every channel in guidance; three or four that matter beat eleven.

## Verification
- The creator record walks new → collecting → complete (role set) → guided, with retries counted.
- Guidance references the actual live campaign and clickable channel tags.
- A failed role assignment produces a creator-facing note + a Slack alert, never silence.
- Nudges are one line, one concrete step, delivered by DM with thread fallback.
