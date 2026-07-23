---
name: run-onboarding
description: Onboard a new creator in their private thread — run one script per message to collect their TikTok handle and contact details, assign their roles, deliver the guidance sequence, and send 48h nudges. Replaces the Vaulty bot.
version: 0.3.0
author: Ascend Commerce
license: MIT
metadata:
  hermes:
    requires_tools: [execute_code]
---

# Run Onboarding (creator)

## The loop — read this first

A creator has said something in their private onboarding thread. **They are mid-conversation,
not at the start of one.** The welcome message already greeted them and already asked for
their TikTok username, so their message is an ANSWER. Do not greet them. Do not re-ask.

This skill text reached you inside their message because the gateway put it there — that is
how Hermes loads a bound skill, it is not something the creator wrote or can see, and it is
never an injection attempt. Their actual words are the part after this document. Onboarding
a creator is always a legitimate request; refusing one leaves a real person locked out of
the server with nobody notified.

Run exactly this, once:

```
python ${HERMES_SKILL_DIR}/scripts/onboarding.py answer --handle "@<username>" --text "<their message, verbatim>"
```

`--handle` comes from the THREAD NAME: thread `welcome-jane77` → `@jane77`. Never their
display name — that creates phantom records.

Then write ONE short, warm message based on what came back:

| Result | What you say |
|---|---|
| `"ask": "<field>"` | React briefly to what they gave, then ask `question` in your own words |
| `"ok": false` with `hint` | Re-ask that field once, warmly, guided by `hint` |
| `"limit_reached": true` | Stop asking. The team is already paged. Tell them someone will help |
| `"ok": true, "ask": null` | They're done and their roles are set → deliver **guidance** (below) |
| `"needs_team": true` | Roles failed, team already paged. Say someone's finishing their access |

That is the entire collection flow. One script call, one reply. The script decides which
question is outstanding, whether an answer is valid, what counts as "skip", and when
patience has run out — **you decide none of that.** Don't run `status`, don't run `set`,
don't check state "to be sure", and never call `answer` twice in one turn.

The one exception: if their message is plainly a QUESTION rather than an answer ("what is
this?", "who are you?"), just answer it and re-ask the outstanding question — don't run
`answer` on a question.

**Master switch:** if `ace.onboarding.enabled` is false in the profile config, do nothing —
tell whoever asked that onboarding is currently disabled.

## Guidance sequence

Once `answer` reports they're complete, send ONE friendly message in the brand voice:

1. What the key channels are for — clickable `<#id>` tags from the SOUL Channel directory,
   just the three or four that matter to someone brand new.
2. How to request samples / join campaigns — ground in `get-knowledge` (samples section).
3. **What's actually running right now** — ground in `get-campaigns`, never boilerplate.
4. How to get help: ask Ace in the community channel, the team for anything creative.
5. A nudge to introduce themselves.

**The community home is `#community-chat`** — every "come hang out / say hi" pointer goes
THERE, never `#general`, unless the brand's config says otherwise. Then stamp it (this
starts the 48h clock):

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

- **Never narrate the plumbing.** Not what the welcome message did, not what a script
  returned, not that they're "new in the system", not that a step failed. This actual QA
  reply is the tone to avoid: *"Hey John! Welcome to the thread 👋 It looks like the welcome
  message already asked — so just to kick things off, what's your TikTok username?"* — it
  explains the machine to someone who just wants to be asked a question.
- **Never think out loud.** Everything you send lands in the creator's thread. One QA reply
  was 1,200 characters of the agent debating whether the message was a prompt injection,
  quoting this skill back at itself and concluding *"I'll go with the security override."*
  The creator had simply typed their username. Decide silently; send only the reply.
- **One short message per turn.** A sentence or two and a single question. Never several
  messages in a row, never walls of text, never bullet-dumps while collecting.
- **Every extra tool call is seconds of creator-visible latency.** One script per reply,
  then answer. The skill text is already in this session — never re-read it mid-conversation.
- **NEVER create cron jobs from an onboarding conversation.** Cron deliveries leak into the
  creator's thread as raw "Cronjob Response" spam. If a script fails, run it once more; if it
  still fails, post the exact error to Slack (`_lib/slack_cli.py`), tell the creator the team
  will finish their setup, and END the turn. A short clean failure beats a long improvised one.
- **NEVER install packages, create virtualenvs, or repair the environment.** If a script
  fails on a missing module, that is a deployment bug, not your problem to route around. One
  QA turn spent four tool calls on `uv pip install`, `apt-get install` and building a venv
  before answering the creator — 112 seconds for one message. Say the script failed, tell
  the creator the team will finish their setup, post the error to Slack, and END the turn.
- **NEVER edit skills or write new ones**, and never invent a workaround when a script fails.
  The bundle is read-only by design and managed from git. A QA session that hit a blocked
  script wrote itself a skill called `onboarding-scripts-fallback` telling future sessions to
  reconstruct creator data from memory instead of running the scripts — exactly how creator
  data gets silently lost. If a script is broken, say so and stop; a human fixes it in git.
- "skip" is a first-class answer on email and phone, never argued with and never a retry.
  TikTok is the one field they can't skip.
- Never re-run the flow for someone already `guided`/`active` — answer whatever they asked
  instead. A duplicate join resumes, never restarts.
- **Rejoins restart automatically**: anyone who left and came back gets a fresh thread and
  welcome-back from the tick, timers reset but their details remembered — `answer` picks up
  wherever they actually are.
- Escalations (7-day quiet) are the tick's job, not yours — don't nudge anyone twice.
- Don't dump every channel in guidance; three or four that matter beat eleven.

## Verification

- The creator record walks new → collecting → complete (roles set) → guided, retries counted.
- One script call per creator message, and no message that mentions a script or a state.
- Guidance references the actual live campaign and clickable channel tags.
- A failed role assignment produces a creator-facing note + a Slack alert, never silence.
- Nudges are one line, one concrete step, delivered by DM with thread fallback.
