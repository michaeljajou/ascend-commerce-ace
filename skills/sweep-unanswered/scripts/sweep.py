#!/usr/bin/env python3
"""Zero-token sweep: find creator messages nobody answered, wake the agent only then.

Runs as the pre-script of a recurring cron job (every 2m). Deterministic, no LLM:
  - prints {"wakeAgent": false}  → silent tick, the agent never runs, zero tokens
  - prints candidate messages    → injected into the agent's prompt (sweep-unanswered skill)

A message is a CANDIDATE when ALL hold:
  - posted in one of the brand's engaged channels (ace.discord.scoping.free_response —
    with the mention-only gateway these are no longer live free-response channels;
    they are the channels this sweep watches)
  - author is a creator: not a bot/webhook, not a team member (ace.discord.team_role)
  - it does not @mention Ace (mentions are answered instantly by the gateway)
  - it is at least ace.discord.sweep_minutes old (default 5) — the team gets first right
    of reply
  - no team member and no bot has posted in that channel after it

State (<profile>/ace/sweep_state.json) tracks the last-seen message per channel — the
first run initializes to "now" (no backfill) — plus the resolved team-role id, bot user
id, and a per-author team-membership cache.

NOTE: this file is copied to <profile>/scripts/ace-sweep.py by setup.py (Hermes only
runs cron scripts from the profile's scripts/ dir) — it must stay self-contained
(stdlib + PyYAML only, no _lib imports).

Usage:
    python sweep.py [--profile-dir <dir>]   # default: $HERMES_HOME
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DISCORD_API = "https://discord.com/api/v10"
MEMBER_CACHE_HOURS = 24
FETCH_LIMIT = 100

SILENT = json.dumps({"wakeAgent": False})


# ── Discord REST (token-efficient: plain GETs, no LLM anywhere) ────────────────

def _get(token: str, path: str):
    req = urllib.request.Request(
        f"{DISCORD_API}{path}",
        headers={"Authorization": f"Bot {token}", "User-Agent": "ace-sweep/0.1"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def bot_token(profile: Path) -> str | None:
    if tok := os.environ.get("DISCORD_BOT_TOKEN"):
        return tok
    env_path = profile / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("DISCORD_BOT_TOKEN="):
                return s.split("=", 1)[1].strip().strip("'\"") or None
    return None


# ── pure candidate selection (unit-tested) ─────────────────────────────────────

def parse_ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def is_bot_author(msg: dict) -> bool:
    return bool((msg.get("author") or {}).get("bot")) or bool(msg.get("webhook_id"))


def mentions_user(msg: dict, user_id: str | None) -> bool:
    return any(u.get("id") == user_id for u in msg.get("mentions") or [])


def select_candidates(
    messages: list[dict],
    *,
    now: datetime,
    threshold: timedelta,
    team_ids: set[str],
    bot_user_id: str | None,
) -> tuple[list[dict], str | None]:
    """(candidates, new_last_seen_id) from a channel's new messages, oldest→newest.

    A later message by ANY responder (team member or bot — incl. Ace's own instant
    @mention replies) marks every earlier message in the channel as answered.
    Messages younger than the threshold stay pending: last_seen does not advance past
    them, so the next tick re-evaluates once the team's 5 minutes are up.
    """
    msgs = sorted(messages, key=lambda m: int(m["id"]))
    answered_until: datetime | None = None  # latest responder timestamp
    for m in msgs:
        author_id = (m.get("author") or {}).get("id")
        if is_bot_author(m) or author_id in team_ids:
            answered_until = parse_ts(m["timestamp"])

    candidates: list[dict] = []
    last_seen: str | None = None
    for m in msgs:
        ts = parse_ts(m["timestamp"])
        author = m.get("author") or {}
        is_creator = not is_bot_author(m) and author.get("id") not in team_ids
        pending = (
            is_creator
            and not mentions_user(m, bot_user_id)
            and (m.get("content") or "").strip()
            and not (answered_until and answered_until > ts)
        )
        if pending and now - ts < threshold:
            break  # too young — leave it (and everything after) for the next tick
        if pending:
            candidates.append(m)
        last_seen = m["id"]
    return candidates, last_seen


# ── main ───────────────────────────────────────────────────────────────────────

def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"channels": {}, "members": {}}


def team_member_ids(state: dict, token: str, guild_id: str, author_ids: set[str],
                    role_id: str | None, now: datetime) -> set[str]:
    """Which of these authors hold the team role (cached; one member GET per new author)."""
    if not role_id:
        return set()
    cache = state.setdefault("members", {})
    team = set()
    for uid in author_ids:
        entry = cache.get(uid)
        if not entry or now - parse_ts(entry["at"]) > timedelta(hours=MEMBER_CACHE_HOURS):
            try:
                member = _get(token, f"/guilds/{guild_id}/members/{uid}")
                entry = {"team": role_id in (member.get("roles") or []), "at": now.isoformat()}
            except urllib.error.HTTPError:
                entry = {"team": False, "at": now.isoformat()}  # left the server, etc.
            cache[uid] = entry
        if entry["team"]:
            team.add(uid)
    return team


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    args = ap.parse_args(argv)
    profile = Path(args.profile_dir)
    now = datetime.now(timezone.utc)

    import yaml

    config = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8")) or {}
    ace_discord = ((config.get("ace") or {}).get("discord")) or {}
    channel_names = (ace_discord.get("scoping") or {}).get("free_response") or []
    guild_id = str(ace_discord.get("guild_id") or "")
    team_role = ace_discord.get("team_role")  # name or numeric id
    threshold = timedelta(minutes=int(ace_discord.get("sweep_minutes", 5)))

    token = bot_token(profile)
    directory_path = profile / "channel_directory.json"
    if not token or not channel_names or not directory_path.exists():
        print(SILENT)  # not fully wired yet — never wake the agent for config gaps
        print("sweep: missing token/channels/channel_directory — skipping.", file=sys.stderr)
        return 0

    directory = json.loads(directory_path.read_text(encoding="utf-8"))
    name_to_id = {c["name"]: c["id"]
                  for c in directory.get("platforms", {}).get("discord", [])
                  if c.get("type") == "channel"}
    swept = {n: name_to_id[n] for n in channel_names if n in name_to_id}

    state_path = profile / "ace" / "sweep_state.json"
    state = load_state(state_path)

    try:
        if not state.get("bot_user_id"):
            state["bot_user_id"] = _get(token, "/users/@me")["id"]
        if team_role and not state.get("team_role_id"):
            roles = _get(token, f"/guilds/{guild_id}/roles")
            match = next((r for r in roles
                          if r["id"] == str(team_role) or r["name"].lower() == str(team_role).lower()), None)
            if match:
                state["team_role_id"] = match["id"]
            else:
                print(f"sweep: team role {team_role!r} not found in guild — treating everyone "
                      "as a creator.", file=sys.stderr)
                state["team_role_id"] = None

        all_candidates: list[dict] = []
        for name, cid in swept.items():
            last_seen = state["channels"].get(cid)
            if last_seen is None:
                # First run: start from now — never backfill old history into replies.
                msgs = _get(token, f"/channels/{cid}/messages?limit=1")
                state["channels"][cid] = msgs[0]["id"] if msgs else "0"
                continue
            msgs = _get(token, f"/channels/{cid}/messages?after={last_seen}&limit={FETCH_LIMIT}")
            if not msgs:
                continue
            author_ids = {(m.get("author") or {}).get("id") for m in msgs
                          if not is_bot_author(m) and m.get("author")}
            team = team_member_ids(state, token, guild_id, author_ids,
                                   state.get("team_role_id"), now)
            picked, new_last_seen = select_candidates(
                msgs, now=now, threshold=threshold, team_ids=team,
                bot_user_id=state.get("bot_user_id"),
            )
            if new_last_seen:
                state["channels"][cid] = new_last_seen
            for m in picked:
                all_candidates.append({
                    "channel": name,
                    "channel_id": cid,
                    "message_id": m["id"],
                    "author": (m.get("author") or {}).get("username"),
                    "posted_at": m["timestamp"],
                    "content": (m.get("content") or "").strip(),
                })
    except (urllib.error.URLError, TimeoutError) as exc:
        print(SILENT)  # transient network problem — skip this tick, no alert spam
        print(f"sweep: transient error, skipping tick: {exc}", file=sys.stderr)
        return 0
    finally:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state), encoding="utf-8")

    if not all_candidates:
        print(SILENT)
        return 0

    print(json.dumps({
        "unanswered_creator_messages": all_candidates,
        "instructions": "Handle per the sweep-unanswered skill: classify each; operational → "
                        "grounded reply via reply.py; creative-strategy → escalate to Slack, NO "
                        "channel reply; off-topic → skip. End your turn with only [SILENT].",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
