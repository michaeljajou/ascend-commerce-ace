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

**Pacing — the #1 rule: ONE short message per turn.** A sentence or two plus a single
question. Never several messages in a row, never walls of text, never bullet-dumps while
collecting info. Run at most the one or two scripts a step needs, then answer — a fast short
reply beats a thorough slow one. You should NOT need `status` on every message: the thread is
your conversation history; run `status` only on your first turn in a thread or when unsure.

**The scripts do the judging, you do the talking.** Pass the creator's answer through
verbatim — do NOT decide yourself whether it's a valid handle, whether "nah" means skip, or
whether they've had too many tries. `set` answers all of that and returns a verdict:

```
python ${HERMES_SKILL_DIR}/scripts/onboarding.py set --handle "@<username>" --tiktok "<exactly what they typed>"
```

- `{"ok": true, ...}` → saved. Move to the next question. `"skipped": ["email"]` means they
  declined that one; acknowledge lightly and move on, never push back.
- `{"ok": false, "reason": "..."}` → re-ask ONCE, warmly and concretely, using the reason:
  `not_a_handle` (ask for just the @name they post under), `looks_like_email` (that's their
  email, you want the TikTok name), `not_an_email`, `not_a_phone`, `blank`,
  `required` (they tried to skip TikTok — say you do need this one, it's the only one).
- `{"limit_reached": true}` → **stop asking.** They're already flagged and the team is
  already pinged. Tell them warmly that someone from the team will finish this with them,
  and end the turn. Do not re-ask, do not run anything else.

Check where they are first (**first turn only**):
`python ${HERMES_SKILL_DIR}/scripts/onboarding.py status --handle "@<username>"`
(if there's no record yet, `start` one). Then continue from the first missing piece:

1. **TikTok username** (required) — the welcome message already asked for it, so your first
   reply should react to their answer, not re-introduce yourself.
2. **Email** (OPTIONAL). Ask like: "What's the best email to reach you? If you prefer not to
   share, just say \"skip\"."
3. **WhatsApp / phone number** (OPTIONAL). Ask like: "Last one — what's your WhatsApp or
   phone number? If you prefer not to share, just say \"skip\"."
4. **Complete** (TikTok collected; email/phone may be skipped). ONE command — it assigns
   every role in `ace.onboarding.creator_roles` (default `onboarded` + `creator`, Vaulty
   parity), then posts their details to the team's **#ace-onboarding** Slack channel:
   ```
   python ${HERMES_SKILL_DIR}/scripts/onboarding.py complete --handle "@<username>"
   ```
   You never need their Discord ID — the script reads it from the record the join tick
   wrote. Do not call `assign_role.py` yourself.
   - `{"ok": true}` → they're in. Go straight to guidance.
   - `{"ok": false, "needs_team": true}` → role assignment failed, which means they're
     still locked out of the server. The team has ALREADY been paged with the error
     (`team_notified`). Tell the creator warmly that someone's finishing their access and
     end the turn. Don't retry it, and don't paste the error to them.
5. **Guidance sequence** — ONE friendly message, in the brand voice, covering in order:
   1. What the key channels are for (use clickable `<#id>` tags from the SOUL Channel directory;
      just the few that matter to someone brand new).
   2. How to request samples / join campaigns — ground in `get-knowledge` (samples section).
   3. **What's actually running right now** — ground in `get-campaigns` (never boilerplate).
   4. How to get help: ask Ace in the community channel, or the team for anything creative.
   5. A nudge to introduce themselves in the community channel.
   **The community home is `#community-chat`** (clickable tag from the Channel directory) —
   every "come hang out / say hi / ask questions" pointer goes THERE. Never point creators
   to `#general` unless the brand's config explicitly says otherwise.
   Then stamp it — the 48h clock starts here:
   ```
   python ${HERMES_SKILL_DIR}/scripts/onboarding.py guided --handle "@<username>"
   ```

## Nudge mode (woken by the tick with `onboarding_nudges_due`)

Only `stage: guided` creators arrive here (setup-reminder nudges for people who never replied
are fixed copy the tick DMs itself). For each entry: write ONE friendly, low-pressure line in
the brand voice pointing at a single concrete next step — prefer the live campaign/challenge
(`get-campaigns`), else "come say hi" in `#community-chat`.
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
- **NEVER edit skills or write new ones**, and never invent a workaround procedure when a
  script fails. The bundle is read-only by design and managed from git. A QA session that
  hit a blocked script wrote itself a skill called `onboarding-scripts-fallback` telling
  future sessions to reconstruct creator data from memory instead of running the scripts —
  which is exactly how creator data gets silently lost. If a script is broken, say so and
  stop; a human fixes it in git.
- **Every extra tool call is seconds of creator-visible latency.** Aim for at most 1–2 script
  runs per reply, then answer. Don't re-read files or re-check state you already have. The
  skill text is already in this session — never re-read it mid-conversation.
- Keep turns short — one question or one step per message. No status chatter, no walls of text.
- The tick already marked them nudged when it woke you — deliver every nudge you were handed;
  if delivery fails both ways, post the failure to Slack instead of dropping it.
- `complete` fails without a TikTok username — that's the guard, not an error to work around.
  Email and phone are optional ("skip" is a first-class answer, never argued with).
- Retries are per-creator and cumulative across all fields — the limit is a total patience
  budget, not per-field. A "skip" is NOT a retry. `set` counts them for you; you do not need
  to call `retry` yourself.
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
