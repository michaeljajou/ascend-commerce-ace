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
✅ 2026-09-10 QBounce — same three faults again (tab-indented `- Description:` product
item, tab + curly-quoted value props); fixed into `name`/`description` pairs, validated
both ends (md5-identical), staged at `/opt/data/staging/qbounce-knowledge.yaml`. Left for
the brand team: `compliance` is empty, and the payment FAQ covers campaign rewards but not
the commission payout schedule.
✅ 2026-09-10 Prime Natural — the three usual faults plus a fourth: the second `compliance`
item dedented to column 0. Fixed, validated both ends, staged. Content catch: commission
`15%` in the section vs `20%` in the FAQ answer — operator confirmed 15%, FAQ corrected
before Step 6. Same payment-FAQ gap as QBounce.

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
4. **OAuth2 → URL Generator** → scope `bot` — or skip the checkbox hunt: the exact URL
   with every needed permission is printed by `prep_server.py` (its `PERMS` table is
   the single source of truth; notably it includes BOTH thread-creation bits — the
   onboarding channel's overwrites deny public threads, and Discord 403s any overwrite
   touching a permission the bot doesn't hold). Open the URL → pick the brand's server
   → Authorize.

**Verify:** bot appears (offline) in the server member list. Intents are re-verified
programmatically at Step 3 via `GET /applications/@me` flags once the token is on the VPS.

**Live run:** ✅ 2026-07-29 I Am Joy — application created, both privileged intents on,
token held by operator for Step 3, bot invited via the URL-generator link. Programmatic
intent/guild verification deferred to Step 3 as designed.

---

## Step 2 — Profile shell + secrets (VPS)

**Who:** Runner creates the profile; Operator drops the one new secret. (Comes BEFORE
server prep so the bot token is on the box — Step 3 is scripted and needs it.)

**Do:**
1. Runner — create the profile by cloning an existing brand (brings the shared secrets
   and the skills bundle; no secret ever transits chat):
   ```
   docker exec hermes-ace hermes profile create <brand> --clone-from test-brand --description "..."
   ```
2. Runner — **immediately scrub the cloned Discord identity** (the clone carries the
   source brand's bot token; if the gateway ever started with it, this profile would
   connect AS the other brand's bot) and repoint the data dir:
   ```
   docker exec hermes-ace sh -c 'sed -i "/^DISCORD_BOT_TOKEN=/d;/^DISCORD_HOME_CHANNEL/d" /opt/data/profiles/<brand>/.env'
   docker exec hermes-ace sh -c 'sed -i "s|^ACE_DATA_DIR=.*|ACE_DATA_DIR=/opt/data/profiles/<brand>/ace|" /opt/data/profiles/<brand>/.env'
   docker exec hermes-ace mkdir -p /opt/data/profiles/<brand>/ace
   ```
3. Operator — append the new bot's token (from Step 1) to the profile `.env`; token value
   never transits chat or this repo:
   ```
   ssh ascomm-vps 'docker exec -i hermes-ace tee -a /opt/data/profiles/<brand>/.env' <<< 'DISCORD_BOT_TOKEN=<paste>'
   ```
4. Runner — verify by key NAMES only (`grep -o "^[A-Z_]*" .env`): `DISCORD_BOT_TOKEN`,
   `ACE_SLACK_BOT_TOKEN`, `OPENROUTER_API_KEY`, `ACE_DATA_DIR`. **Never** store the Slack
   token under the name `SLACK_BOT_TOKEN` in a brand `.env` — that name makes the Hermes
   gateway treat the brand as a Slack platform and retry-connect forever.

**Verify:** the four keys present; no second `DISCORD_BOT_TOKEN` line (readers take the
FIRST match — a stale cloned line would win over the operator's).

**Live run:** ✅ 2026-07-29 I Am Joy — shell created via `--clone-from test-brand`
(clone warned "no API keys yet" but the `.env` came through; keys verified by name),
cloned `DISCORD_BOT_TOKEN`/`DISCORD_HOME_CHANNEL` scrubbed, `ACE_DATA_DIR` was still
pointing at test-brand's data dir — repointed (real trap: two brands silently sharing
one knowledge/creator store). Operator token drop verified: exactly one
`DISCORD_BOT_TOKEN` line, five keys present. Bonus catch: the token was valid but the
bot was in ZERO guilds — the Step 1 invite click had never been completed; the script's
zero-guild error now prints the exact invite URL as the fix.
✅ 2026-09-10 QBounce — shell created as **uid 10000** (`-u 10000 -e HOME=/opt/data`), so
no chown is needed later; `--clone-from` copies only config.yaml/.env/SOUL.md/skills (no
state.db, cron store, or data). Scrubbed the cloned token/home channel, repointed
`ACE_DATA_DIR`, and also blanked the cloned `discord.free_response_channels` (test-brand's
onboarding channel id) ahead of first connect. Operator token drop pending.
✅ 2026-09-10 Prime Natural — same as QBounce (uid 10000 clone, scrub, repoint, blank the
cloned free-response id); `spec.json` written with `onboarding.enabled: false` from the
start. Token drop verified: one line, five keys.

---

## Step 3 — Server prep (scripted + human residue)

**Who:** Runner runs the script; Operator does the residue.

**Do:**
1. Runner — dry-run, read the plan, then apply:
   ```
   docker exec hermes-ace /opt/hermes/.venv/bin/python3 \
     /opt/data/ascend-commerce-ace/skills/setup-brand/scripts/prep_server.py \
     --profile-dir /opt/data/profiles/<brand> \
     --avatar-file /opt/data/ascend-commerce-ace/assets/ace-avatar.png \
     --channels <every channel named in knowledge.yaml>          # then: --apply
   ```
   The script (idempotent) does everything the API allows:
   - creates the missing roles (**Ascend Team**, **onboarded**, **creator** — new roles
     land at the bottom of the list, i.e. below the bot, exactly where the bot needs
     them to be assignable); pre-existing roles at/above the bot are reported for a
     human drag, never moved;
   - creates the missing text channels (**#agent-ace** always, plus the brand list —
     names must match `knowledge.yaml` exactly or Ace's channel references degrade to
     plain text);
   - reads back the **Step 1 privileged-intent toggles** from `/applications/@me`
     (fails loudly if one is off) and prints the **guild_id** needed in Step 4;
   - **audits the bot's own guild permissions** and prints the invite URL that fixes
     any gap (a bot can't grant itself permissions; re-opening the URL re-grants in
     place, nobody is kicked);
   - sets the bot's server **nickname** (default `Ace`) and its **avatar** from the
     canonical repo asset `assets/ace-avatar.png` (only when the bot has none — a
     custom face is never clobbered; `--avatar-from-profile <dir>` copies from an
     existing brand's bot instead).
2. Operator — the residue the API can't reach:
   - Turn **Vaulty's join handling OFF** on this server (it's Vaulty's config, not ours);
     two greeters means duplicate onboarding spaces and role conflicts.
   - Assign **Ascend Team** to every human team member (it gates the reply-sweep, staff
     visibility, and never-onboard filtering).
   - Optionally drag the new channels into categories (cosmetic).
3. Answer the branch question: **fresh server or existing live community?** — decides
   Step 8.

**Verify:** re-run the dry-run — `create` lists empty, both intents `true`, no
`misplaced` roles.

**Live run:** ✅ 2026-08-04 I Am Joy (scripted half) — this is the LIVE community
(150+ per-creator channels, Vaulty visibly active). Three catches, all now encoded:
(1) all six brand channels existed under emoji-decorated names (`📢│announcements`) —
exact-name matching would have created seven duplicates; channel matching now goes
through `channel_slug` (e39cc33), which also future-proofs resolve_channels.
(2) Vaulty's `Onboarded`/`Creator` roles already exist — ADOPTED rather than
duplicated (assign_role + gate match case-insensitively); members holding them are
pre-grandfathered for the Step 8 gate. Both sit ABOVE the bot → operator drag needed.
(3) `/applications/@me` reported BOTH intents OFF despite Step 1 — portal toggles
hadn't stuck. Applied: `#agent-ace` + `Ascend Team` created, nickname `Ace` set,
avatar already present (untouched), permissions complete, re-run is a no-op.
Residue open: intent toggles, role drag, Ascend Team assignment, Vaulty off.
✅ 2026-09-10 QBounce (scripted half) — existing community on the same agency template
(19 humans, Growi bot, per-creator channels, Vaulty roles). Dry run: both intents on first
try, permissions complete, all six brand channels present under decorated names,
`Ascend Team`/`Onboarded`/`Creator` all pre-existing and ALL above the bot's role
(`Ace – Qbounce` sat at position 1 — bottom of the list). Applied: `#agent-ace` created,
nickname `Ace` set, avatar already present; re-run is a no-op. Also found a pre-existing
`onboarding` channel built for Vaulty (an `Onboarding` role sees it, @everyone cannot,
no bot entry) — the resolver now adopts it and applies the door permissions (Step 5).
Residue open: drag the bot's role above the three roles, assign Ascend Team (0 holders),
Vaulty off.
✅ 2026-09-10 Prime Natural (scripted half) — the biggest server yet: 302 humans, 202 text
channels, 13 categories, and Vaulty genuinely ACTIVE here (bots: Carl-bot, Ticket Tool,
Growi, Vaulty, client-reporting-agent, Euka Creators 2). `Ascend Team` already held by 8;
Onboarded 186 / Creator 176 / role-less 3; base role View already off. No existing
`onboarding` channel. Applied: `#agent-ace` created, nickname set, avatar present, intents
and permissions complete. Residue open: bot role `Ace` at position 1 (drag above
`Ascend Team` at 15), Vaulty join handling OFF (real this time).

---

## Step 4 — Brand spec + setup.py (VPS)

**Who:** Runner.

**Do:**
1. Write the spec JSON: `brand_id`, `brand_name`, `discord.guild_id` (from Step 3),
   channel behavior map (mirror an existing brand's mapping as baseline: community-chat
   POST_ANSWER, our-products ANSWER, announcements POST_ONLY, etc.), `slack_channel`,
   `model` (mirror the pilot-proven config), and **`onboarding.enabled: false`** — it flips
   to true at go-live (Step 9). `ace.onboarding.enabled` is a LIVE switch: the fleet join
   listener rescans every profile every 60s and connects as the brand's bot the moment it
   is true, so the bot shows online and joins start onboarding threads while the gateway
   is still down (QBounce, 2026-09-10).
2. Store the spec at `<profile>/spec.json` (documents the brand; makes re-runs one
   command), then run `python skills/setup-brand/scripts/setup.py --spec
   <profile>/spec.json --profile-dir <profile>` (via the Hermes venv in the container).
   Writes `config.yaml`, `SOUL.md`, `cronjobs.yaml`, merges `ACE_DATA_DIR` into `.env`,
   and applies the security hardening automatically (approvals, strict code execution,
   command allowlist, reduced toolset, silenced chatter channels — see SKILL.md 3a; do
   not hand-edit these away).
3. **`chown -R hermes:hermes <profile>` after every setup run** — operator commands run
   as root in the container, but the gateway and all agent scripts run as uid 10000; a
   root-owned profile can't write its own state.

**Verify:** `config.yaml` scoping matches the intended channel map; `SOUL.md` carries the
brand voice + locked rules; `ACE_DATA_DIR=<profile>/ace` in `.env`; and
`ace.onboarding.channel_id` is ABSENT (on a cloned profile it must not carry the source
brand's — setup.py drops a foreign one automatically since a0d4bd2).

**Live run:** ✅ 2026-08-04 I Am Joy — spec stored in-profile, channels mirrored from
test-brand semantics (challenges upgraded POST_ONLY→POST_ANSWER: this brand runs weekly
challenge Q&A). Catches: (1) the cloned config carried TEST-BRAND's
`onboarding.channel_id` and the merge preserved it — guard added (a0d4bd2) + one-time
manual drop (the pre-guard run had already re-stamped it under the new guild);
(2) root-owned profile after setup → chown step added; (3) sweep resolved engaged
channels by EXACT directory name and would have watched zero of this server's
emoji-decorated channels — slug fix (0856ce3), test-brand's installed copy refreshed
too. Root model/providers survived the merge (inherited from clone); hardening
verified applied.
✅ 2026-09-10 QBounce — spec mirrors I Am Joy's map with the six knowledge-file channels
active (community-chat FULL_ACTIVE, our-products/how-to-level-up ANSWER,
campaigns/challenges POST_ANSWER, announcements POST_ONLY), creator-wins/success-stories
MONITOR_ONLY, everything else INACTIVE; per-creator channels left unlisted. setup.py run
as uid 10000 (no chown needed); model inherited from the clone (`deepseek/deepseek-v4-flash`
via OpenRouter, `fallback_providers: []`); hardening verified; foreign
`onboarding.channel_id` dropped as designed.
✅ 2026-09-10 Prime Natural — identical spec shape (six active channels, MONITOR pair,
INACTIVE list, per-creator channels unlisted), `onboarding.enabled: false`; setup.py as
uid 10000, hardening verified, model inherited.

---

## Step 5 — First gateway connect + resolve_channels (VPS)

**Who:** Runner.

**Do:** channel IDs don't exist until the bot connects once.
1. `hermes --profile <brand> gateway run` → wait for "Channel directory built: N target(s)"
   with N > 0 → stop it.
2. `python skills/setup-brand/scripts/resolve_channels.py --profile-dir <profile_dir>
   --wire-onboarding` — the flag wires the onboarding channel while the brand is still
   paused (`onboarding.enabled: false`, see Step 4). Wires the mention-only gateway
   (`require_mention: true`), `DISCORD_HOME_CHANNEL`
   (#agent-ace), the SOUL.md channel directory, and the onboarding channel (creates
   #onboarding, binds it as the sole free-response channel, binds `run-onboarding`).
   A server that already has an `onboarding` channel (Vaulty's) gets it ADOPTED by name,
   with the door permissions applied per overwrite — Vaulty's own role entry is left alone.
3. Do NOT restart the gateway for a brand still being onboarded — it stays down through
   Steps 6–8 and comes up at the Step 9 smoke test (see the pause/resume ops note).
   Gateway invocation on this box: `docker exec -d -u 10000 -e HOME=/opt/data hermes-ace
   hermes --profile <brand> gateway run`.

**Verify:** `channel_directory.json` exists with N > 0 channels; `config.yaml` has
`require_mention: true` and `ace.onboarding.channel_id`; SOUL.md channel map lists the
real `<#id>`s; `cronjobs.yaml` has `weekly-reminders` delivering to `discord:<numeric id>`
(the script's `cron_deliver` summary line).

**Live run:** ✅ 2026-08-04 I Am Joy — connected ~60s as uid 10000, directory built
(178 channels, decorated names), stopped. Before first connect, scrubbed two more
cloned leftovers: root `discord.free_response_channels` and `channel_skill_bindings`
still pointed at test-brand's onboarding channel. resolve_channels then 403'd creating
#onboarding: its overwrites DENY public threads and Discord rejects (50013) overwrites
touching permissions the bot doesn't hold — **Create Public Threads** was missing from
the original invite set; added to prep_server PERMS (audit + URL), operator re-clicked,
resolve succeeded: #onboarding `1534273465333321831`, five swept channels resolved via
slugs, home `#agent-ace` wired, SOUL directory written. Gateway left DOWN by design.
✅ 2026-09-10 QBounce — first connect built the directory in ~12s (31 channels), stopped.
Resolver run with `--wire-onboarding` on the PAUSED brand: adopted Vaulty's existing
`onboarding` channel (`1544367029614547007`) and applied the door overwrites per PUT
(no 403s — the pre-existing entries only touched View/Send), five swept channels
resolved via slugs, home `#agent-ace` wired, SOUL directory written, `weekly-reminders`
target rewritten to `discord:1544367029614547011`. Catch of the day: after Step 4 the
fleet join listener had connected as the QBounce bot within a minute (spec said
`enabled: true`) — bot showed online mid-onboarding; spec flipped to false, setup.py
re-run, listener dropped it on the next rescan. Gateway left DOWN.
✅ 2026-09-10 Prime Natural — first connect built 203 targets in ~12s; resolver with
`--wire-onboarding` CREATED `#onboarding` (`1547691523070496800`) with the door design
(no 403 — the Create Public Threads bit has been in PERMS since I Am Joy), five swept
channels resolved, home `#agent-ace` `1547691197118685254`, SOUL directory 200 entries,
reminders target `discord:1402018857715109991`. Gateway DOWN, brand paused.

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

**Verify:** BOTH paths — the venv (parsed) path returns a slice on-topic and EMPTY
off-topic (the escalate signal), and the sandbox path (uid 10000, `/usr/bin/python3`)
prints the raw file (the no-PyYAML fallback can't subset, so never test emptiness there).

**Live run:** ✅ 2026-08-04 I Am Joy — staged file copied in, hermes-owned; venv:
commission query returned the FAQ slice, "wifi password" returned empty; sandbox as
uid 10000: raw fallback served the file.
✅ 2026-09-10 QBounce — copied in as uid 10000 (md5-identical to the staged file);
venv: "commission rate" returned the FAQ slice, "wifi password" empty; sandbox as uid
10000: raw fallback served the file.
✅ 2026-09-10 Prime Natural — same, after the 15% correction (md5 7e26c17a…).

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
Plus daily-digest and the other blueprint jobs (mirror the pilot brand's set:
daily-digest, nudge-inactive, sweep-unanswered, onboarding-tick, weekly-reminders).
**weekly-reminders takes its `--deliver` from the resolved `cronjobs.yaml`
(`discord:<numeric id>`), never `discord:#name`** — Hermes resolves a name by exact
directory match, so a decorated channel 404s on every run while the job reports "ok"
(I Am Joy delivered nothing for a month; found 2026-09-10 via the ⚠ line in `cron list
--all`). Fix a registered job in place: `cron edit <job_id> --deliver discord:<id>`.

**Hermes wraps every cron delivery** in `Cronjob Response: <job> (job_id: …)` above the
text and `To stop or manage this job, send me a new message…` below it unless
`cron.wrap_response: false` is in the profile's config.yaml. `setup.py` forces it from
2026-09-22; brands set up earlier need the key added by hand (no gateway restart: the
scheduler re-reads config.yaml on each delivery). Found 2026-09-21: QBounce and Prime
Natural creators had seen the wrapper on every reminder since 9/10, and the Monday run's
`HTTP 402` failure summary landed in both `#announcements` — a failed job delivers its
error to the same target as a success, so a job that posts publicly cannot fail privately.

Gotchas (all bit): run cron commands as **`-u 10000 -e HOME=/opt/data`** — the cron
store is HOME-relative, so jobs created as root live in a different store than the
scheduler reads. **Immediately `cron pause` every job** for a brand not yet live
(sweep/onboarding-tick fire within 2 minutes of creation and talk to Discord via REST
even with the gateway down). `cron list` hides paused jobs — use `--all`.

**Verify:** `cron list --all` shows the full set paused (pre-live) or active (live);
at go-live, force one sweep tick and confirm a quiet tick spends zero tokens.

**Live run:** ✅ 2026-08-04 I Am Joy — five jobs registered as uid 10000 +
HOME=/opt/data, paused within the same minute (sweep's first fire was 2 minutes out),
`cron list --all` confirms all five paused. Resume happens at Step 9.
✅ 2026-09-10 QBounce — five jobs created as uid 10000 in one pass and paused within the
same minute; none had run. `weekly-reminders` registered straight to the numeric id from
the resolved `cronjobs.yaml`.
✅ 2026-09-10 Prime Natural — same (one scripted pass: create ×5 then pause ×5).

---

## Step 8 — Access gate (VPS) — BRANCHES on fresh vs existing community

**Who:** Runner.

The gate lives on the **@everyone base role** (View Channels off; creator/staff/bot roles
carry their own View) — category overwrites alone do NOT reach unsynced child channels
(QA 2026-07-23: eleven channels leaked to a fresh join). Fail-closed for channels created
later; the onboarding channel keeps an explicit @everyone ALLOW — the only open door.

**Do:**
1. **Existing community only:** members already holding the adopted creator roles
   (e.g. Vaulty's `Onboarded`/`Creator`) keep access automatically — the gate grants
   view to those roles. The decision is about ROLE-LESS current members: bulk-assign
   `creator` (`skills/run-onboarding/scripts/assign_role.py`) to grandfather them, or
   leave them gated so they funnel through Ace onboarding. Decide with the operator
   BEFORE `--apply` — the gate hides the server from role-less members instantly.
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
The Step 9 throwaway-account join doubles as this check.

**Live run:** ✅ 2026-08-04 I Am Joy — operator chose NOT to grandfather role-less
members (the dry run then showed the base role already had View off — the server was
already Vaulty-gated, so that choice costs nothing). Plan: grant sight to `Onboarded`
+ `Ascend Team` (Creator/bot already sighted), gate 8 categories/orphans incl. the
onboarding door and the ops channel (staff+bot only — exception shipped this run),
7 private categories left untouched, zero leaky children. BLOCKED pre-apply by the
fenced-category guard: 👥 Community, 🏠 Home, 🎓 Free Mentorship deny @everyone with
no bot allow — the bot can neither manage NOR READ them (the sweep needs Community!).
Operator must add the bot's role → View Channel on those three categories; apply
refuses (exit 1) until then, so nothing partial was written.
APPLY (after the category fix): base-role grants + #new-members + #agent-ace +
#onboarding door landed. Five belt writes on Vaulty-walled structures failed 50013 —
Discord requires the editor to hold every bit in the overwrite set being replaced, and
Vaulty's walls carry bits the bot lacks there. EXPECTED on pre-walled servers; the
acceptance test is COMPUTED effective visibility, not the write log: role-less member
sees exactly [#onboarding, #welcome] (welcome-mat kept deliberately); Onboarded/Creator
member sees all 18 community channels. One more unsynced-children strike: the bot's
category grants did NOT reach the engaged channels (own overwrites) — bot read 403 on
all five; operator adds Ace's role per-CHANNEL (View + Read History + Send) on the six
engaged/post channels. Never "Sync to category" — it would erase Vaulty's per-channel
role allows. CLOSED after the operator's per-channel grants: all six engaged/post
channels verified view=Y send=Y history=Y by computation AND live reads OK.
✅ 2026-09-10 QBounce — operator chose no grandfathering (base role already View-off).
Dry run blocked by the fenced-category guard on `🏠 Home` and `👥 Community` (same as I Am
Joy) → operator granted the bot's role View on both categories → apply: base role grants
`Onboarded`; `#new-members`, `#welcome`, the `#onboarding` door and `#agent-ace` gated;
the two category belt writes failed 50013 (expected — they already deny @everyone).
Leaks accepted by the operator: `create-ticket` (and `coaching-calls`) stay visible.
COMPUTED visibility: role-less member sees exactly [#onboarding, #create-ticket];
Onboarded 16 channels; Creator 8 (Vaulty tiering — completion assigns both roles, so the
union applies). Same unsynced-children strike as I Am Joy: all six engaged/post channels
carry their own `@everyone deny View` with no bot entry, so the category grant did not
reach them — bot view=n on all six, and Send missing on announcements/challenges/
our-products. Operator adds `Ace – Qbounce` per channel (View + Send + Read History);
the gate is otherwise CLOSED. UI note that cost a round trip: on a channel's Permissions
page the simple "private channel" list grants ONLY View when a role is added; Send needs
the **Advanced permissions** expander (role on the left, three-state toggles on the
right). CLOSED after the per-channel grants: all six view=Y history=Y by computation,
live reads OK on all six; Send=Y everywhere except `our-products` (read-only channel —
creators can't post there, so nothing to answer in place).
✅ 2026-09-10 Prime Natural — guard blocked on FOUR fenced categories (`🏠 Home`,
`👥 Community`, `🎓 Free Mentorship`, `🛠️ Support`); operator granted the bot's role on the
categories AND per channel in one round (the QBounce lesson, given up front) → apply:
base role grants `Onboarded`; `#new-members`, `💰 Paid Collabs Support`, `#agent-ace` and
the `#onboarding` door gated; five belt writes 50013 on Vaulty-walled structures
(`❤️│welcome` + the four categories) — expected, they already deny @everyone. COMPUTED:
role-less sees [welcome, onboarding, challenges] (welcome = the welcome mat as on I Am
Joy; `🏅│challenges` re-allows @everyone — operator's call), Onboarded/Creator 20 each,
bot view+history+read OK on all engaged channels, Send everywhere except `challenges`
(operator adds it — challenge posts go there). Bot role dragged to 18, above all three.

---

## Step 9 — Smoke test (both)

**Who:** Runner drives; Operator (or a throwaway account) plays creator.

**Do:**
0. Go live: set `onboarding.enabled: true` in `<profile>/spec.json`, re-run `setup.py`
   (keeps the Step 5 wiring and `channel_id`), start the gateway, resume the crons. The
   join listener picks the brand up within 60s.
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

**Live run:** 🔄 2026-08-04 I Am Joy — operator chose to launch directly in PROD mode
(no test-mode: it only compresses the two onboarding timers, and the happy path +
community QA don't need it). All five crons resumed, gateway up as uid 10000. The
throwaway-account walk-through (fresh join → gate proof → onboarding → community QA)
runs against the live system with real timers — sweep replies land ~10–12 min after
an untagged question.
🔄 2026-09-10 QBounce — PROD mode like I Am Joy. Go-live pass: `spec.json`
`onboarding.enabled: true` → setup.py re-run (kept `channel_id`, free-response and
binding from the paused wiring) → gateway up as uid 10000 (connected as Ace#8714 in ~4s;
the first `gateway list` right after `docker exec -d` raced the PID file and said "not
running" — poll, don't trust the first read) → five crons resumed → join listener
re-attached within a minute; first sweep and onboarding ticks ran quiet (`wakeAgent=false`,
zero API calls). Went live 14:32 ET with the OpenRouter balance at $8.56 and no top-up in
sight — operator's call. Throwaway walk-through pending.
🔄 2026-09-10 Prime Natural — same go-live pass, 15:50 ET: gateway connected as Ace#7309
in ~9s (204 targets), five crons resumed, listener attached within the minute, first
sweep tick quiet (`wakeAgent=false`). Post-live permission audit (overwrite map on the
engaged channels + categories): grants carry only the bot's role; no stray member or
role entries; `🏅│challenges` still has NO entry for the bot (Send missing — challenge
posts need it) and keeps its @everyone View allow. The bot cannot read the guild audit
log (no View Audit Log in the invite set) — before/after computed visibility is the
evidence that no other role's sight changed. Walk-through pending; Vaulty-off not
verifiable by API.

**Catches from the first month live (read from the profile's `state.db` sweep sessions and
the channels themselves, 2026-09-04):** (1) the brand posts every campaign and announcement
through a Discord **webhook** ("I Am Joy Brand"), text inside an embed — `get-campaigns`
dropped webhook posts as bots and empty-content posts as blank, so `#campaigns` read
`active: null` with a live monthly campaign up (2026-08-28, 2026-09-03) and two creators were
told nothing was running; the Growi "Mega Campaign" also lived only in `#announcements`,
which the script never read. Fixed: webhook posts count as team posts, embeds are read,
`#announcements` is fetched as a `recent` feed. (2) Both sweep replies went through
`reply.py --text "..."` in the terminal tool: bash left `\n` literal and ate `$5` from `$50`
("win 0!"). Fixed: text goes over stdin in a quoted heredoc; `reply.py` repairs `\n`.
(3) Neither reply tagged the creator — `allowed_mentions` without `replied_user` and a bare
username in the text. Fixed: `replied_user: true`, the payload carries `author_id`/`mention`,
`reply.py --mention`. (4) The 2026-09-03 escalation never reached Slack: the agent guessed
`<bundle>/_lib/…` without `skills/`, found nothing, gave up. Fixed: the sweep payload lists
the scripts by absolute path. Deploy note: `ace-sweep.py` is a COPY in `<profile>/scripts/`
— a `git pull` alone does not update it; re-copy it (or re-run setup.py) per brand.
(5) 2026-09-10: `weekly-reminders` had never delivered (name target vs decorated channel,
see Step 7); repointed to the id and **left paused** until the operator reviews the
composed output — the Sept 7 run prefixed the post with a data recap, so the skill now
carries an output-only contract. Resume with `cron resume 7a30c4a702b0`.
(6) 2026-09-21: the OpenRouter balance ran down (≈$10 of $720 left) and the Monday
`weekly-reminders` run 402'd on QBounce and Prime Natural; Hermes delivered the failure
summary, wrapped in its cron boilerplate, into both brands' public `#announcements`
(see the wrap_response note in Step 7). `cron.wrap_response: false` applied fleet-wide.

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

## Ops note — pausing / resuming a brand

Inviting the bot to a server activates NOTHING: it sits offline until its profile's
gateway runs. A brand is "live" only while two things run, and each pauses independently:

- **Gateway** (live listening: mentions, DMs, onboarding threads):
  `hermes --profile <brand> gateway stop` → bot shows offline, hears nothing.
  Resume with `gateway run` (how this box runs it) or `gateway start` if installed as a
  service. `gateway list` shows every profile's state.
- **Cron jobs** (sweep, digest — these fire even with the gateway down, because the
  scripts talk to Discord via REST): `hermes --profile <brand> cron pause <job>` /
  `cron resume <job>`; `cron list` to see them.

- **Fleet join listener** (one process for all brands, `ace-join-listener.py`): it
  rescans every profile every 60s and holds a Discord connection for every brand whose
  `ace.onboarding.enabled` is true — the bot shows ONLINE and a join opens an onboarding
  thread even with the gateway down. Pausing a brand for the listener means setting
  `onboarding.enabled: false` in the spec and re-running `setup.py`; it drops the
  connection on the next rescan ("dropped a connection (brand disabled)" in
  `/opt/data/logs/ace-join-listener.log`).

During onboarding (this SOP), a new brand is fully paused by default: no gateway, no
crons until Steps 5/7, `onboarding.enabled: false` until Step 9 — and the Step 5 first
connect is deliberately brief (build directory → stop). Leave the gateway down through
Steps 6–8 and bring it up for the Step 9 smoke test.

---

## Known decisions still open (flagged during pilot)
- `fallback_providers` for the model config — decide before multi-brand rollout.
- Welcome-back fast-track (leave + rejoin) — untested path.
