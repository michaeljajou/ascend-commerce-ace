#!/usr/bin/env python3
"""Zero-token onboarding tick: joins, leavers, engagement, timers — agent only for nudges.

Runs as the pre-script of a recurring cron job (every 2m), like ace-sweep.py. Deterministic:
prints {"wakeAgent": false} on idle ticks (the agent never runs, zero tokens); wakes the agent
ONLY to compose nudge DMs. Everything else is plain REST + SQLite:

  1. JOINS   — polls the guild member list (needs the Server Members privileged intent) and
     diffs against the store. A new human, non-team member gets a private thread under the
     brand's #onboarding channel, an @add, and the brand welcome + TikTok-username ask —
     no LLM involved. The first-ever tick baselines existing members as `pre_existing`
     (Vaulty-era creators are never re-onboarded).
  2. LEAVERS — mid-flow members who left: timers stop, state=left, thread archived.
  3. ENGAGEMENT — new messages anywhere the bot can see mark guided/nudged creators active
     (posts and commands count; reactions are a documented phase-1 gap).
  4. TIMERS  — computed from stored timestamps every tick, so downtime never silently skips:
     guided + nudge window with no engagement → nudge candidates (wake agent → DM);
     joined + escalation window, still quiet → Slack escalation posted BY THIS SCRIPT
     (brand-tagged, zero tokens), then ✅-reaction polling auto-resolves the case.
  5. ARCHIVE — closed-out threads are archived after the configured window.

Master switch: ace.onboarding.enabled (default false) — the whole tick is inert until the
operator flips it. test_mode compresses the windows to minutes for QA.

NOTE: copied to <profile>/scripts/ace-onboarding-tick.py by setup.py — must stay
self-contained (stdlib + PyYAML; no _lib imports; carries its own schema migration mirror).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DISCORD_API = "https://discord.com/api/v10"
SLACK_API = "https://slack.com/api"
UA = "DiscordBot (https://github.com/michaeljajou/ascend-commerce-ace, 0.1)"
SILENT = json.dumps({"wakeAgent": False})
RESOLVE_EMOJI = "white_check_mark"  # ✅ on the Slack escalation = one-click resolve

# Mirror of _lib/store.py ONBOARDING_MIGRATIONS — update both together.
MIGRATIONS = [
    """CREATE TABLE IF NOT EXISTS creators (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        handle           TEXT UNIQUE NOT NULL,
        tiktok           TEXT,
        email            TEXT,
        role             TEXT,
        onboarding_state TEXT DEFAULT 'new',
        joined_at        TEXT,
        last_active_at   TEXT
    )""",
    "ALTER TABLE creators ADD COLUMN discord_id TEXT",
    "ALTER TABLE creators ADD COLUMN thread_id TEXT",
    "ALTER TABLE creators ADD COLUMN retries INTEGER DEFAULT 0",
    "ALTER TABLE creators ADD COLUMN guided_at TEXT",
    "ALTER TABLE creators ADD COLUMN nudged_at TEXT",
    "ALTER TABLE creators ADD COLUMN escalated_at TEXT",
    "ALTER TABLE creators ADD COLUMN escalation_channel TEXT",
    "ALTER TABLE creators ADD COLUMN escalation_ts TEXT",
    "ALTER TABLE creators ADD COLUMN resolved_at TEXT",
    "ALTER TABLE creators ADD COLUMN phone TEXT",
]

DEFAULT_WELCOME = (
    "Hey {mention} — welcome to the {brand} creator community! 🎉\n\n"
    "I'm Ace, the community assistant. This private space is just for you and the team — "
    "let's get you set up in under a minute.\n\n"
    "**First up: what's your TikTok username?** (just reply here)"
)
DEFAULT_WELCOME_BACK = (
    "Hey {mention} — welcome back to {brand}! 🎉\n\n"
    "I'm Ace. Leaving the server cleared your access, so let's get you set back up — "
    "it only takes a moment. **Just reply here and I'll take care of the rest.**"
)
# The setup-reminder DM (creator never replied to the welcome). FIXED copy, sent by
# this script directly — zero tokens, and the wording can never drift.
NUDGE_DM = (
    "Hey! Just a friendly reminder to complete the onboarding steps to join the {brand} "
    "discord community! It takes 1 minute and the thread is waiting for you here: {link}. "
    "Excited to have you in the community!"
)


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def discord(token: str, path: str, payload: dict | None = None, method: str | None = None):
    req = urllib.request.Request(
        f"{DISCORD_API}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                 "User-Agent": UA},
        method=method or ("POST" if payload is not None else "GET"),
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body.strip() else {}


def slack(token: str, method: str, payload: dict):
    req = urllib.request.Request(
        f"{SLACK_API}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8", "User-Agent": "ace-onboarding/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def env_token(profile: Path, key: str) -> str | None:
    if tok := os.environ.get(key):
        return tok
    env_path = profile / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith(f"{key}="):
                return s.split("=", 1)[1].strip().strip("'\"") or None
    return None


# ── pure decision helpers (unit-tested) ────────────────────────────────────────

def effective_windows(ob: dict) -> tuple[timedelta, timedelta]:
    """(nudge_window, escalate_window) honoring test_mode."""
    if ob.get("test_mode"):
        return (timedelta(minutes=float(ob.get("test_nudge_minutes", 3))),
                timedelta(minutes=float(ob.get("test_escalate_minutes", 8))))
    return (timedelta(hours=float(ob.get("nudge_hours", 48))),
            timedelta(days=float(ob.get("escalate_days", 7))))


def is_new_joiner(member: dict, known_ids: set[str], team_role_id: str | None) -> bool:
    user = member.get("user") or {}
    if user.get("bot") or not user.get("id"):
        return False
    if user["id"] in known_ids:
        return False
    if team_role_id and team_role_id in (member.get("roles") or []):
        return False  # team members joining a server are never onboarded
    return True


def due_nudges(rows: list[dict], now: datetime, nudge_window: timedelta) -> list[dict]:
    """Quiet creators due a nudge, never nudged before:
    - guided:     the window runs from guidance completion (the normal case)
    - collecting: they NEVER replied to the welcome — the window runs from joining
      (without this they'd sit in collecting forever with no timer at all)."""
    out = []
    for r in rows:
        if r["onboarding_state"] not in ("guided", "collecting") or r.get("nudged_at"):
            continue
        anchor = r.get("guided_at") if r["onboarding_state"] == "guided" else r.get("joined_at")
        if not anchor:
            continue
        if now - datetime.fromtimestamp(float(anchor), tz=timezone.utc) >= nudge_window:
            out.append(r)
    return out


def due_escalations(rows: list[dict], now: datetime, escalate_window: timedelta) -> list[dict]:
    """Still quiet after the escalation window since JOINING — whether they finished
    guidance, got nudged, or never replied to the welcome at all (collecting)."""
    out = []
    for r in rows:
        if r["onboarding_state"] not in ("guided", "nudged", "collecting") or not r.get("joined_at"):
            continue
        if now - datetime.fromtimestamp(float(r["joined_at"]), tz=timezone.utc) >= escalate_window:
            out.append(r)
    return out


def escalation_text(row: dict, brand: str, now: datetime) -> str:
    joined = datetime.fromtimestamp(float(row["joined_at"]), tz=timezone.utc)
    days = (now - joined).days
    done = []
    if row.get("tiktok"):
        done.append(f"gave TikTok ({row['tiktok']})")
    if row.get("email"):
        done.append("gave email")
    if row.get("guided_at"):
        done.append("finished guidance")
    if row.get("nudged_at"):
        done.append("was nudged, no response")
    return (
        f"[{brand}] ⏰ Onboarding escalation: *{row['handle']}* joined {days}d ago "
        f"({joined.date().isoformat()}) and hasn't engaged anywhere in the server.\n"
        f"So far: {', '.join(done) or 'nothing — never replied in onboarding'}.\n"
        f"Profile: <https://discord.com/users/{row.get('discord_id') or ''}>\n"
        f"React with ✅ once you've handled it — that closes the case."
    )


# ── db helpers (standalone mirror of the store contract) ──────────────────────

def acquire_lock(profile: Path):
    """One tick at a time: the cron run and listener-triggered runs must not overlap
    (a race could double-onboard a joiner). Returns the held lock fd, or None if busy."""
    import fcntl

    lock_path = profile / "ace" / "onboarding_tick.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        fd.close()
        return None


def pid_alive(pid_path: Path) -> int | None:
    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)  # alive?
        return pid
    except (OSError, ValueError):
        return None


def shared_root(profile: Path) -> Path:
    """Fleet root for the SHARED join listener: <root>/profiles/<brand> → <root>.
    Degenerate case (no profiles/ parent): the profile itself."""
    p = profile.resolve()
    return p.parents[1] if p.parent.name == "profiles" else p


def ensure_listener(profile: Path, enabled: bool) -> None:
    """Watchdog for the SHARED instant-join listener (one process serves every brand —
    ~40MB total instead of ~55MB per brand). Any enabled brand's tick may respawn it;
    the listener discovers all enabled brands itself and exits when none remain, so a
    disabled brand never has to kill it. The 2-minute poll stays as the fallback —
    the listener is a latency upgrade, not a dependency."""
    import signal
    import subprocess

    # Migration: kill a legacy per-profile listener from the pre-fleet version.
    legacy_pid_path = profile / "ace" / "onboarding_listener.pid"
    if legacy := pid_alive(legacy_pid_path):
        try:
            os.kill(legacy, signal.SIGTERM)
            legacy_pid_path.unlink(missing_ok=True)
            print("onboarding: stopped the legacy per-brand listener (fleet listener replaces it).",
                  file=sys.stderr)
        except OSError:
            pass

    listener = profile / "scripts" / "ace-join-listener.py"
    if not enabled or not listener.exists():
        return
    root = shared_root(profile)
    if pid_alive(root / "ace-join-listener.pid"):
        return
    # Several brands' ticks can race here — one spawner wins via a fleet-level lock.
    import fcntl

    try:
        spawn_lock = open(root / "ace-join-listener.lock", "w")
        fcntl.flock(spawn_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return
    try:
        if pid_alive(root / "ace-join-listener.pid"):
            return
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log = open(log_dir / "ace-join-listener.log", "ab")
        subprocess.Popen(
            [sys.executable, str(listener), "--profile-dir", str(profile)],
            stdout=log, stderr=log, start_new_session=True,
        )
        print("onboarding: started the fleet join listener.", file=sys.stderr)
    finally:
        spawn_lock.close()


def open_db(profile: Path) -> sqlite3.Connection:
    db = profile / "ace" / "ace.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    for m in MIGRATIONS:
        try:
            conn.execute(m)
        except sqlite3.OperationalError:
            pass
    return conn


def upd(conn, handle: str, **fields) -> None:
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE creators SET {assignments} WHERE handle = ?", (*fields.values(), handle))
    conn.commit()


# ── tick steps ─────────────────────────────────────────────────────────────────

def list_all_members(token: str, guild_id: str) -> list[dict]:
    members, after = [], "0"
    while True:
        page = discord(token, f"/guilds/{guild_id}/members?limit=1000&after={after}")
        members.extend(page)
        if len(page) < 1000:
            return members
        after = max((m["user"]["id"] for m in page if m.get("user")), key=int)


def onboard_new_member(conn, token: str, member: dict, cfg: dict, now: datetime) -> None:
    user = member["user"]
    handle = f"@{user['username']}"
    channel_id = cfg["channel_id"]
    # Re-onboarding (rejoin / team reset): the old private thread is dead weight —
    # leaving the server revoked their access to it. Archive it, start fresh.
    old = conn.execute(
        "SELECT thread_id, tiktok FROM creators WHERE handle = ? OR discord_id = ?",
        (handle, user["id"]),
    ).fetchone()
    returning = bool(old and old["tiktok"])  # we already know them → welcome-back variant
    if old and old["thread_id"]:
        archive_thread(token, old["thread_id"])
    thread = discord(token, f"/channels/{channel_id}/threads", {
        "name": f"welcome-{user['username']}"[:100],
        "type": 12,                      # private thread
        "invitable": False,
        "auto_archive_duration": 10080,  # a week of inactivity before Discord auto-hides it
    })
    discord(token, f"/channels/{thread['id']}/thread-members/{user['id']}", {}, method="PUT")
    template = DEFAULT_WELCOME_BACK if returning else (cfg.get("welcome_message") or DEFAULT_WELCOME)
    welcome = template.format(
        mention=f"<@{user['id']}>", brand=cfg.get("brand_name") or "the brand")
    discord(token, f"/channels/{thread['id']}/messages", {
        "content": welcome, "allowed_mentions": {"parse": ["users"]},
    })
    # Fresh lifecycle, remembered identity: timers/retries/escalation reset so every
    # window starts over, but tiktok/email survive — a returning creator who already
    # gave them gets fast-tracked to role assignment instead of being re-interrogated.
    conn.execute(
        """INSERT INTO creators (handle, onboarding_state, joined_at, discord_id, thread_id)
           VALUES (?, 'collecting', ?, ?, ?)
           ON CONFLICT(handle) DO UPDATE SET
             onboarding_state='collecting', discord_id=excluded.discord_id,
             thread_id=excluded.thread_id, joined_at=excluded.joined_at,
             retries=0, guided_at=NULL, nudged_at=NULL, escalated_at=NULL,
             escalation_channel=NULL, escalation_ts=NULL, resolved_at=NULL,
             last_active_at=NULL""",
        (handle, str(now.timestamp()), user["id"], str(thread["id"])),
    )
    conn.commit()
    print(f"onboarding: started {handle} (thread {thread['id']})", file=sys.stderr)


def send_dm(token: str, user_id: str, text: str) -> bool:
    try:
        dm = discord(token, "/users/@me/channels", {"recipient_id": user_id})
        discord(token, f"/channels/{dm['id']}/messages", {"content": text})
        return True
    except urllib.error.HTTPError as exc:
        print(f"onboarding: DM to {user_id} failed ({exc.code}) — falling back to thread.",
              file=sys.stderr)
        return False


def archive_thread(token: str, thread_id: str) -> None:
    try:
        discord(token, f"/channels/{thread_id}", {"archived": True, "locked": False}, method="PATCH")
    except urllib.error.HTTPError as exc:
        print(f"onboarding: could not archive thread {thread_id}: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    ap.add_argument("--joins-only", action="store_true",
                    help="member sync only (used by the instant-join listener); timers, "
                         "engagement, and escalations stay with the cron run, which is the "
                         "only run that can wake the agent")
    args = ap.parse_args(argv)
    profile = Path(args.profile_dir)
    now = datetime.now(timezone.utc)

    import yaml

    config = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8")) or {}
    ace = config.get("ace") or {}
    ob = ace.get("onboarding") or {}
    if not args.joins_only:  # the cron run supervises the listener (start/stop with the switch)
        ensure_listener(profile, bool(ob.get("enabled")))
    if not ob.get("enabled"):
        print(SILENT)  # master switch off — the whole workflow is inert
        return 0

    lock = acquire_lock(profile)
    if lock is None:
        print(SILENT)  # another run (cron or listener-triggered) is mid-flight
        return 0

    token = env_token(profile, "DISCORD_BOT_TOKEN")
    guild_id = str((ace.get("discord") or {}).get("guild_id") or "")
    channel_id = str(ob.get("channel_id") or "")
    if not token or not guild_id or not channel_id:
        print(SILENT)
        print("onboarding: missing token/guild/channel_id — run setup + resolve_channels first.",
              file=sys.stderr)
        return 0

    state_path = profile / "ace" / "onboarding_tick_state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    state.setdefault("cursors", {})

    conn = open_db(profile)
    cfg = {**ob, "brand_name": ace.get("brand_name") or ace.get("brand_id")}
    nudge_window, escalate_window = effective_windows(ob)
    team_role_id = state.get("team_role_id")
    wake: list[dict] = []

    try:
        # resolve team role once (team members are never onboarded)
        team_role = (ace.get("discord") or {}).get("team_role")
        if team_role and not team_role_id:
            roles = discord(token, f"/guilds/{guild_id}/roles")
            match = next((r for r in roles if r["id"] == str(team_role)
                          or r["name"].lower() == str(team_role).lower()), None)
            team_role_id = state["team_role_id"] = match["id"] if match else None

        # 1+2. member sync: joins + leavers
        members = list_all_members(token, guild_id)
        member_ids = {m["user"]["id"] for m in members if m.get("user")}
        # Not "known" (so the member sync re-onboards them when present):
        #   'new'  — the team's reset command ("re-onboard me")
        #   'left' — they left the server; being in the member list again means they
        #            REJOINED, and rejoins auto-restart onboarding (Discord stripped
        #            their roles on the way out, so they need the flow again anyway).
        # Everyone else present is either mid-flow, done, or an open case — untouched.
        known = {r["discord_id"] for r in conn.execute(
            "SELECT discord_id FROM creators WHERE discord_id IS NOT NULL"
            " AND onboarding_state NOT IN ('new', 'left')")}
        if not state.get("member_baseline_done"):
            # First enabled tick: existing members were onboarded by Vaulty — record, don't re-run.
            for m in members:
                user = m.get("user") or {}
                if user.get("bot") or not user.get("id") or user["id"] in known:
                    continue
                conn.execute(
                    """INSERT INTO creators (handle, onboarding_state, discord_id)
                       VALUES (?, 'pre_existing', ?) ON CONFLICT(handle) DO NOTHING""",
                    (f"@{user['username']}", user["id"]),
                )
            conn.commit()
            state["member_baseline_done"] = True
            print(f"onboarding: baselined {len(members)} existing members (no re-onboarding).",
                  file=sys.stderr)
        else:
            for m in members:
                if is_new_joiner(m, known, team_role_id):
                    onboard_new_member(conn, token, m, {**cfg, "channel_id": channel_id}, now)
            # Leavers: ANY tracked state moves to 'left' (timers stop, thread archived) —
            # including escalated/resolved/active, so a later REJOIN auto-restarts the
            # flow. Only Vaulty-era pre_existing members are never touched.
            tracked = conn.execute(
                """SELECT * FROM creators WHERE discord_id IS NOT NULL
                   AND onboarding_state IN ('collecting','complete','guided','nudged',
                                            'flagged','escalated','resolved','active')"""
            ).fetchall()
            for r in tracked:
                if r["discord_id"] not in member_ids:
                    upd(conn, r["handle"], onboarding_state="left")
                    if r["thread_id"]:
                        archive_thread(token, r["thread_id"])
                    print(f"onboarding: {r['handle']} left ({r['onboarding_state']}) — "
                          "timers stopped; a rejoin restarts the flow.", file=sys.stderr)

        if args.joins_only:
            print(SILENT)  # joins/leavers handled; everything else belongs to the cron run
            return 0

        # 3. engagement scan: any post anywhere → guided/nudged creators become active
        directory_path = profile / "channel_directory.json"
        if directory_path.exists():
            directory = json.loads(directory_path.read_text(encoding="utf-8"))
            watch_ids = {r["discord_id"]: r["handle"] for r in conn.execute(
                "SELECT discord_id, handle FROM creators WHERE onboarding_state IN ('guided','nudged')"
            ) if r["discord_id"]}
            for c in directory.get("platforms", {}).get("discord", []):
                if c.get("type") != "channel" or c["id"] == channel_id:
                    continue
                cursor = state["cursors"].get(c["id"])
                if cursor is None:
                    try:
                        msgs = discord(token, f"/channels/{c['id']}/messages?limit=1")
                    except urllib.error.HTTPError:
                        continue  # channel the bot can't read (private) — skip, retry next tick
                    state["cursors"][c["id"]] = msgs[0]["id"] if msgs else "0"
                    continue
                try:
                    msgs = discord(token, f"/channels/{c['id']}/messages?after={cursor}&limit=100")
                except urllib.error.HTTPError:
                    continue  # channel the bot can't read — skip
                if msgs:
                    state["cursors"][c["id"]] = str(max(int(m["id"]) for m in msgs))
                for m in msgs:
                    uid = (m.get("author") or {}).get("id")
                    if uid in watch_ids:
                        upd(conn, watch_ids[uid], onboarding_state="active",
                            last_active_at=str(now.timestamp()))
                        print(f"onboarding: {watch_ids[uid]} engaged — timers stopped.", file=sys.stderr)

        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM creators WHERE onboarding_state IN "
            "('collecting','guided','nudged','escalated')"
        )]

        # 4a. nudges — mark on emit (at-most-once):
        #   collecting (never replied to the welcome): FIXED reminder copy → this script
        #   DMs it directly, zero tokens. guided (finished setup, went quiet): the agent
        #   composes a campaign-flavored nudge in the brand voice → wake it.
        for r in due_nudges(rows, now, nudge_window):
            upd(conn, r["handle"], onboarding_state="nudged", nudged_at=str(now.timestamp()))
            if r["onboarding_state"] == "collecting":
                link = f"https://discord.com/channels/{guild_id}/{r['thread_id']}"
                text = NUDGE_DM.format(brand=cfg["brand_name"], link=link)
                if not send_dm(token, r["discord_id"], text) and r["thread_id"]:
                    discord(token, f"/channels/{r['thread_id']}/messages", {
                        "content": text.replace(f" here: {link}", " right here"),
                        "allowed_mentions": {"parse": ["users"]}})
                continue
            wake.append({"handle": r["handle"], "discord_id": r["discord_id"],
                         "thread_id": r["thread_id"], "nudge_via": ob.get("nudge_via", "dm"),
                         "stage": r["onboarding_state"]})

        # 4b. escalations → pure-script Slack post, zero tokens
        # (ACE_ prefix: a bare SLACK_BOT_TOKEN makes the gateway retry a Slack platform forever)
        slack_token = env_token(profile, "ACE_SLACK_BOT_TOKEN") or env_token(profile, "SLACK_BOT_TOKEN")
        for r in due_escalations(rows, now, escalate_window):
            if not slack_token:
                print("onboarding: escalation due but no SLACK_BOT_TOKEN — skipping.", file=sys.stderr)
                break
            result = slack(slack_token, "chat.postMessage", {
                "channel": ob.get("slack_channel") or ace.get("slack_channel") or "#ace-escalations",
                "text": escalation_text(r, cfg["brand_name"], now),
            })
            if result.get("ok"):
                upd(conn, r["handle"], onboarding_state="escalated",
                    escalated_at=str(now.timestamp()),
                    escalation_channel=result.get("channel"), escalation_ts=result.get("ts"))
            else:
                print(f"onboarding: Slack escalation failed: {result.get('error')}", file=sys.stderr)

        # 4c. ✅ reaction on the escalation post = one-click resolve
        if slack_token:
            for r in rows:
                if r["onboarding_state"] != "escalated" or not r.get("escalation_ts"):
                    continue
                got = slack(slack_token, "reactions.get", {
                    "channel": r["escalation_channel"], "timestamp": r["escalation_ts"]})
                reactions = ((got.get("message") or {}).get("reactions")) or []
                if any(x.get("name") == RESOLVE_EMOJI for x in reactions):
                    upd(conn, r["handle"], onboarding_state="resolved",
                        resolved_at=str(now.timestamp()))
                    if r.get("thread_id"):
                        archive_thread(token, r["thread_id"])
                    print(f"onboarding: {r['handle']} resolved via ✅.", file=sys.stderr)

        # 5. archive closed-out threads after the configured window
        archive_after = timedelta(days=float(ob.get("archive_days", 7)))
        for r in conn.execute(
            """SELECT handle, thread_id, last_active_at, resolved_at FROM creators
               WHERE thread_id IS NOT NULL AND onboarding_state IN ('active','resolved')"""
        ).fetchall():
            anchor = r["resolved_at"] or r["last_active_at"]
            if anchor and now - datetime.fromtimestamp(float(anchor), tz=timezone.utc) >= archive_after:
                archive_thread(token, r["thread_id"])
                upd(conn, r["handle"], thread_id=None)

    except (urllib.error.URLError, TimeoutError) as exc:
        print(SILENT)
        print(f"onboarding: transient error, skipping tick: {exc}", file=sys.stderr)
        return 0
    finally:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state), encoding="utf-8")

    if not wake:
        print(SILENT)
        return 0
    print(json.dumps({
        "onboarding_nudges_due": wake,
        "instructions": "Send each creator their 48h nudge per the run-onboarding skill "
                        "(Nudge mode): friendly, low-pressure, ONE concrete next step grounded "
                        "in the live campaign. Deliver per nudge_via. End with only [SILENT].",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
