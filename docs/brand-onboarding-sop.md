# SOP — Onboarding a Brand onto Ace

End-to-end procedure for taking a brand from "we want Ace in our community" to live.
Two actors: the **Operator** (human — Discord portal clicks, server settings, secrets) and the
**Runner** (Claude / an engineer on the VPS — everything scriptable). Canonical deep reference
for the VPS side: [skills/setup-brand/SKILL.md](../skills/setup-brand/SKILL.md).

**Living document.** Each step carries a *Live run* log line from the brands that executed it.
Steps not yet validated live are marked ⏳ — finalize the exact commands when a real run
confirms them. Never write secret values into this file.

Order matters: knowledge → portal → server prep → profile/secrets → spec → first connect →
knowledge in place → crons → gate → smoke test → live. The gate (step 8) MUST come after
roles exist (step 2) and — for an existing community — after bulk role assignment, or every
current member instantly loses sight of the server.

---

## Step 0 — Author and validate the brand knowledge file

**Who:** brand team writes, Runner validates.

**Do:**
1. Copy `skills/setup-brand/templates/knowledge.template.yaml`, fill it out with the brand
   team, save as `knowledge.yaml`. Required sections: `brand`, `faq` (target 30–40 entries;
   7–10 is acceptable for a pilot — every escalation afterward names the FAQ entry to add).
2. Products as `name`/`description` pairs. Drop the `campaigns` section — `get-campaigns`
   reads #campaigns/#challenges live.
3. Validate with the real loader (repo checkout):
   ```
   .venv/bin/python3 -c "import sys; sys.path.insert(0,'skills'); from _lib import knowledge; \
     kb = knowledge.load_knowledge('<path>'); print(knowledge.validate(kb) or 'PASS')"
   ```
   Probe a few queries with `skills/get-knowledge/scripts/get.py --path <path> --query "..."`
   — on-topic returns a slice, off-topic returns empty (the escalate signal).
4. Stage on the VPS: `/opt/data/staging/<brand>-knowledge.yaml` (inside `hermes-ace`),
   re-validate there with `/opt/hermes/.venv/bin/python3`.

**Pitfalls (all hit for real):** rich-text editors insert tabs (YAML forbids them — file
won't parse) and curly quotes (parse as content, not delimiters); a dedented list item kills
the whole parse; a `- Description:` sibling item attaches the description to nothing. Move
the file as a file — never copy/paste through an editor. Watch for marketing copy that
contradicts the brand's own `compliance` rules: Ace repeats this file verbatim and creators
echo Ace into videos.

**Verify:** `validate: PASS` locally AND in the container; probe queries return the right
sections; off-topic query returns empty.

**Live run:** ✅ 2026-07-29 I Am Joy — validated both ends, staged at
`/opt/data/staging/i-am-joy-knowledge.yaml`. Caught live: tabs + curly quotes from a
rich-text editor, detached `- Description:` items, dedented compliance rule.

---

## Step 1 — Discord application (Developer Portal)

**Who:** Operator, at <https://discord.com/developers/applications>.

**One bot per brand.** Sharing a bot token across brand profiles makes every profile's
gateway hear every guild — cross-brand bleed. The bot's *username* can be "Ace" for all
brands (server nickname disambiguates if Discord forces a suffix).

**Do:**
1. **New Application** → name it (e.g. "Ace — <Brand>").
2. **Bot** tab → enable **Message Content Intent** and **Server Members Intent** (both
   privileged toggles; Save). Message Content = bot can read messages at all; Server
   Members = the onboarding join poll and role lookups.
3. **Bot** tab → **Reset Token** → copy it somewhere safe for Step 3. It is shown once.
4. **OAuth2 → URL Generator** → scope `bot` → permissions: **Manage Roles, Manage
   Channels, Manage Threads, View Channels, Send Messages, Send Messages in Threads,
   Create Private Threads, Read Message History, Add Reactions, Embed Links, Mention
   Everyone** → open the generated URL → invite the bot into the brand's server.

**Verify:** bot appears (offline) in the server member list. Intents are re-verified
programmatically at Step 3 via `GET /applications/@me` flags once the token is on the VPS.

**Live run:** ⏳ I Am Joy — pending.

---

## Step 2 — Server prep (Discord Server Settings)

**Who:** Operator, in the brand's server.

**Do:**
1. **Roles:** create **Ascend Team**, **onboarded**, **creator**. Drag `onboarded` and
   `creator` **below the bot's role** (Discord forbids assigning roles at/above the
   assigner's own top role). Assign **Ascend Team** to every human team member — it gates
   the reply-sweep (team replies release Ace), staff visibility, and never-onboard filtering.
2. **Channels:** create **#agent-ace** (Ace's ops/output channel). Confirm every channel
   named in `knowledge.yaml` exists with exactly that name — for I Am Joy:
   #announcements, #community-chat, #our-products, #campaigns, #challenges,
   #how-to-level-up. (Name mismatch degrades Ace's channel references from clickable
   links to plain text.)
3. **Vaulty:** turn its join handling OFF on this server before onboarding is enabled —
   two greeters means duplicate onboarding spaces and role conflicts.
4. Note whether this is a **fresh server or an existing live community** — it decides the
   Step 8 branch.

**Verify:** roles exist in the right order; #agent-ace + knowledge channels present;
Vaulty join handling off.

**Live run:** ⏳ I Am Joy — pending.

---

## Step 3 — Profile shell + secrets (VPS)

**Who:** Runner creates the profile; Operator drops the one new secret.

**Do:**
1. Runner: create the Hermes profile for the brand (`hermes` CLI on the VPS — exact
   command recorded on first live run ⏳).
2. Operator: place the Discord bot token in the profile `.env` (Runner supplies the exact
   one-liner with the real profile path; token value never transits chat or this repo):
   ```
   ssh ascomm-vps "docker exec -i hermes-ace sh -c 'echo DISCORD_BOT_TOKEN=<paste> >> /opt/data/profiles/<brand>/.env'"
   ```
3. Runner: copy shared secrets from an existing brand profile's `.env` on the box:
   `ACE_SLACK_BOT_TOKEN` (same Slack workspace — bot already in #ace-escalations and
   #ace-onboarding) and the OpenRouter key. **Never** store the Slack token under the name
   `SLACK_BOT_TOKEN` in a brand `.env` — that name makes the Hermes gateway treat the brand
   as a Slack platform and retry-connect forever.
4. Runner: verify the Discord token + intents via REST (`/applications/@me`,
   `/users/@me/guilds`) — also yields the **guild_id** for Step 4. Discord REST requires a
   `DiscordBot (<url>, <version>)` User-Agent or Cloudflare 403s.

**Verify:** `.env` holds `DISCORD_BOT_TOKEN`, `ACE_SLACK_BOT_TOKEN`, OpenRouter key;
`/applications/@me` flags show both privileged intents; `/users/@me/guilds` lists the brand
guild.

**Live run:** ⏳ I Am Joy — pending.

---

## Step 4 — Brand spec + setup.py (VPS)

**Who:** Runner.

**Do:**
1. Write the spec JSON: `brand_id`, `brand_name`, `discord.guild_id` (from Step 3),
   channel behavior map (mirror an existing brand's mapping as baseline: community-chat
   POST_ANSWER, our-products ANSWER, announcements POST_ONLY, etc.), `slack_channel`,
   `model` (mirror the pilot-proven config), `ace.onboarding.enabled: true`.
2. Run `python skills/setup-brand/scripts/setup.py --spec <spec.json>` (via the Hermes venv
   in the container). Writes `config.yaml`, `SOUL.md`, `cronjobs.yaml`, merges
   `ACE_DATA_DIR` into `.env`, and applies the security hardening automatically
   (approvals, strict code execution, command allowlist, reduced toolset, silenced chatter
   channels — see SKILL.md 3a; do not hand-edit these away).

**Verify:** `config.yaml` scoping matches the intended channel map; `SOUL.md` carries the
brand voice + locked rules; `ACE_DATA_DIR=<profile>/ace` in `.env`.

**Live run:** ⏳ I Am Joy — pending.

---

## Step 5 — First gateway connect + resolve_channels (VPS)

**Who:** Runner.

**Do:** channel IDs don't exist until the bot connects once.
1. `hermes --profile <brand> gateway run` → wait for "Channel directory built: N target(s)"
   with N > 0 → stop it.
2. `python skills/setup-brand/scripts/resolve_channels.py --profile-dir <profile_dir>` —
   wires the mention-only gateway (`require_mention: true`), `DISCORD_HOME_CHANNEL`
   (#agent-ace), the SOUL.md channel directory, and the onboarding channel (creates
   #onboarding, binds it as the sole free-response channel, binds `run-onboarding`).
3. Restart the gateway (the profile's supervised service).

**Verify:** gateway log shows the directory; `config.yaml` has `require_mention: true` and
`ace.onboarding.channel_id`; SOUL.md channel map lists the real `<#id>`s.

**Live run:** ⏳ I Am Joy — pending.

---

## Step 6 — Knowledge file into place (VPS)

**Who:** Runner.

**Do:**
1. Copy the staged file: `/opt/data/staging/<brand>-knowledge.yaml` →
   `<profile>/ace/knowledge.yaml`.
2. `chown 10000` — agent scripts run as uid 10000; a root-owned file is unreadable to them.
3. Validate through the agent's OWN interpreter (`/usr/bin/python3`, no PyYAML — exercises
   the raw-text fallback): `python3 skills/get-knowledge/scripts/get.py --section brand`
   with the profile's `ACE_DATA_DIR`.

**Verify:** sandbox `get.py` returns the brand section; off-topic `--query` returns empty.

**Live run:** ⏳ I Am Joy — pending.

---

## Step 7 — Cron jobs (VPS)

**Who:** Runner.

**Do:** register from the profile's `cronjobs.yaml` / blueprint suggestions. The
non-negotiable one is **sweep-unanswered** with its zero-token pre-script gate:
```
hermes --profile <brand> cron create "every 2m" --name sweep-unanswered \
  --skill sweep-unanswered --script ace-sweep.py --deliver discord \
  "Handle the unanswered creator messages surfaced above, following the sweep-unanswered skill exactly. End with only [SILENT]."
```
Plus daily-digest and the other blueprint jobs (mirror the pilot brand's set).

**Verify:** `hermes --profile <brand> cron list`; force one sweep tick and confirm a quiet
tick spends zero tokens ("ok" with nothing to do).

**Live run:** ⏳ I Am Joy — pending.

---

## Step 8 — Access gate (VPS) — BRANCHES on fresh vs existing community

**Who:** Runner.

The gate lives on the **@everyone base role** (View Channels off; creator/staff/bot roles
carry their own View) — category overwrites alone do NOT reach unsynced child channels
(QA 2026-07-23: eleven channels leaked to a fresh join). Fail-closed for channels created
later; the onboarding channel keeps an explicit @everyone ALLOW — the only open door.

**Do:**
1. **Existing community only:** bulk-assign `creator` to every current human member FIRST
   (`skills/run-onboarding/scripts/assign_role.py`) — otherwise applying the gate hides the
   entire server from all of them at once. New joins from then on go through Ace.
2. Dry-run, then apply:
   ```
   python skills/setup-brand/scripts/gate_channels.py --profile-dir <profile_dir>
   python skills/setup-brand/scripts/gate_channels.py --profile-dir <profile_dir> --apply
   ```
   (`--apply --open` reverses. Re-run after adding channels — new channels are gated by
   default via the base role, but category tidiness is kept.)
3. Verify the role matrix from the script summary: `@everyone view=n`; staff, bot,
   `onboarded`, `creator` all `view=Y`.

**Verify:** a role-less test account joining fresh sees ONLY #onboarding (screenshot-level
check — the 2026-07-23 lesson is that reading back category overwrites is NOT proof).

**Live run:** ⏳ I Am Joy — pending.

---

## Step 9 — Smoke test (both)

**Who:** Runner drives; Operator (or a throwaway account) plays creator.

**Do:**
1. Test-mode ON (short join-poll/reminder windows) for the QA pass.
2. Fresh account joins → sees only #onboarding → private thread opens → complete the
   conversation → `onboarded`+`creator` assigned → channels appear → captured details
   posted to Slack #ace-onboarding, brand-tagged.
3. Community QA: untagged operational question in #community-chat → sweep answers grounded
   within ~grace+2m; creative/strategy question → silent Slack escalation, properly
   formatted; @mention → instant reply.
4. Test-mode OFF (restore real 48h/7d windows). Strip test roles with
   `assign_role.py --remove`, park test threads.

**Verify:** every arrow above observed for real; `onboarding.py trace --handle @<test>`
shows the completed run; no FAILED cron rows in the scheduler.

**Live run:** ⏳ I Am Joy — pending.

---

## Step 10 — Go live + first-week watch

**Who:** Operator announces; Runner watches.

**Do:** point creators at the server. For the first days: watch Slack #ace-escalations
(each repeated escalation = the next FAQ entry to add to `knowledge.yaml` — edits apply on
next read, no restart), read the daily digest, spot-check
`skills/_lib/agent_trace.py --list` for failed runs.

**Verify:** first real creator onboards end-to-end without staff help; escalations arrive
formatted and brand-tagged; digest cron green.

**Live run:** ⏳ I Am Joy — pending.

---

## Known decisions still open (flagged during pilot)
- `fallback_providers` for the model config — decide before multi-brand rollout.
- Welcome-back fast-track (leave + rejoin) — untested path.
