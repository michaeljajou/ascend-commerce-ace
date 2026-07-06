#!/usr/bin/env python3
"""Resolve Discord channel NAMES to numeric IDs, post-connect, and wire them in.

Why this is a separate step: Discord channel IDs don't exist in the brand
spec (the operator only knows channel *names* when writing it). The mapping is
only knowable after the brand's gateway has connected to Discord at least once
and built the profile's channel_directory.json.

What it wires (all idempotent):
  1. Mention-only gateway: `discord.require_mention: true` and
     `discord.free_response_channels` CLEARED. Ace answers @mentions and DMs
     instantly and hears nothing else live — team announcements can never get
     an accidental reply. Unanswered creator messages in the engaged channels
     are handled by the zero-token sweep cron instead (sweep-unanswered skill).
  2. `DISCORD_HOME_CHANNEL` / `DISCORD_HOME_CHANNEL_NAME` in the profile .env —
     Ace's proactive-output channel (cron results, notifications), resolved
     from `ace.discord.home_channel` (default: agent-ace).
  3. The "Channel directory" managed block in SOUL.md — the live
     `#name → <#id>` map so Ace renders clickable channel mentions.
     write_profile preserves this block across setup re-runs.

Run this AFTER the first successful `hermes --profile <brand> gateway run`
connects to Discord (check for "Channel directory built: N target(s)" with
N > 0 in the logs), then restart the gateway once more to pick up the
resolved IDs.

Usage:
    python resolve_channels.py --profile-dir <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # → sibling setup.py
from setup import (  # noqa: E402
    CHANNEL_DIR_END,
    CHANNEL_DIR_START,
    ensure_env,
    upsert_channel_directory,
)

DEFAULT_HOME_CHANNEL = "agent-ace"
ONBOARDING_CHANNEL_NAME = "onboarding"
UA = "DiscordBot (https://github.com/michaeljajou/ascend-commerce-ace, 0.1)"

# Discord permission bits (see the design note in ensure_onboarding_channel)
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
MANAGE_THREADS = 1 << 34
CREATE_PUBLIC_THREADS = 1 << 35
CREATE_PRIVATE_THREADS = 1 << 36
SEND_MESSAGES_IN_THREADS = 1 << 38


def _discord(token: str, path: str, payload: dict | None = None):
    """Tiny Discord REST helper (monkeypatched in tests)."""
    import urllib.request

    req = urllib.request.Request(
        "https://discord.com/api/v10" + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                 "User-Agent": UA},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def bot_token(profile: Path) -> str | None:
    import os

    if tok := os.environ.get("DISCORD_BOT_TOKEN"):
        return tok
    env_path = profile / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("DISCORD_BOT_TOKEN="):
                return s.split("=", 1)[1].strip().strip("'\"") or None
    return None


def ensure_onboarding_channel(profile: Path, ace_cfg: dict, name_to_id: dict[str, str]) -> str | None:
    """Create (or find) the #onboarding parent channel and return its id.

    Design: the channel is VISIBLE to everyone (Discord requires parent-channel view
    to see a private thread) but nobody can post or create threads at channel level —
    creators only ever interact inside their own private thread (which they CAN post
    in), staff (Manage Threads) can see all threads.
    """
    ob = ace_cfg.get("onboarding") or {}
    name = str(ob.get("channel_name") or ONBOARDING_CHANNEL_NAME)
    if existing := name_to_id.get(name):
        return existing

    token = bot_token(profile)
    guild_id = str((ace_cfg.get("discord") or {}).get("guild_id") or "")
    if not token or not guild_id:
        print("WARNING: can't create the onboarding channel (missing token/guild).", file=sys.stderr)
        return None

    roles = _discord(token, f"/guilds/{guild_id}/roles")
    staff_name = str(ob.get("staff_role") or (ace_cfg.get("discord") or {}).get("team_role") or "")
    staff = next((r for r in roles if r["name"].lower() == staff_name.lower()
                  or r["id"] == staff_name), None)
    me = _discord(token, "/users/@me")

    overwrites = [
        {   # @everyone: may view (required to see their own private thread) + reply in threads,
            # but never post at channel level or open threads themselves
            "id": guild_id, "type": 0,
            "allow": str(SEND_MESSAGES_IN_THREADS),
            "deny": str(SEND_MESSAGES | CREATE_PUBLIC_THREADS | CREATE_PRIVATE_THREADS),
        },
        {   # the bot: full working set for creating/managing the private threads
            "id": me["id"], "type": 1,
            "allow": str(VIEW_CHANNEL | SEND_MESSAGES | CREATE_PRIVATE_THREADS
                         | SEND_MESSAGES_IN_THREADS | MANAGE_THREADS),
        },
    ]
    if staff:
        overwrites.append({  # staff: see + manage every onboarding thread
            "id": staff["id"], "type": 0,
            "allow": str(VIEW_CHANNEL | SEND_MESSAGES | MANAGE_THREADS | SEND_MESSAGES_IN_THREADS),
        })
    else:
        print(f"WARNING: staff role {staff_name!r} not found — staff thread access not granted.",
              file=sys.stderr)

    created = _discord(token, f"/guilds/{guild_id}/channels", {
        "name": name, "type": 0,
        "topic": "Private onboarding — Ace opens a personal thread here for every new creator.",
        "permission_overwrites": overwrites,
    })
    print(f"created #{name} ({created['id']})", file=sys.stderr)
    return str(created["id"])


def build_directory_block(name_to_id: dict[str, str]) -> str:
    lines = [
        CHANNEL_DIR_START,
        "## Channel directory (auto-generated — do not edit)",
        "When you mention any of these channels, use the clickable tag exactly as shown:",
    ]
    lines += [f"- #{name} → <#{cid}>" for name, cid in sorted(name_to_id.items())]
    lines.append(CHANNEL_DIR_END)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", required=True)
    args = ap.parse_args(argv)

    profile = Path(args.profile_dir)
    config_path = profile / "config.yaml"
    directory_path = profile / "channel_directory.json"

    if not directory_path.exists():
        print(
            f"ERROR: {directory_path} not found. Run the gateway once so it connects "
            "to Discord and builds the channel directory, then re-run this script.",
            file=sys.stderr,
        )
        return 1

    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    ace_discord = ((config.get("ace") or {}).get("discord")) or {}
    scoping = ace_discord.get("scoping") or {}
    free_response_names = set(scoping.get("free_response", []))

    directory = json.loads(directory_path.read_text(encoding="utf-8"))
    discord_channels = directory.get("platforms", {}).get("discord", [])
    name_to_id = {c["name"]: c["id"] for c in discord_channels if c.get("type") == "channel"}
    if not name_to_id:
        print("No channels in the directory — is the bot actually in the server yet?", file=sys.stderr)
        return 1

    # 1. Mention-only gateway. free_response_channels stays EMPTY on purpose: live
    # replies happen only on @mention/DM; the engaged channels (scoping.free_response)
    # are watched by the ace-sweep.py cron script, which wakes the agent only for
    # creator messages the team hasn't answered within the grace window.
    # SOLE exception: the hidden #onboarding parent channel (when onboarding is enabled) —
    # its private threads inherit free-response, making the onboarding conversation
    # work without @mentions, while every public channel stays mention-only.
    missing = sorted(free_response_names - name_to_id.keys())
    if missing:
        print(f"WARNING: engaged channel(s) not yet seen by the bot: {missing}", file=sys.stderr)
    discord_block = config.setdefault("discord", {})
    discord_block["require_mention"] = True
    discord_block["free_response_channels"] = ""

    onboarding_channel = None
    ace_cfg = config.get("ace") or {}
    if (ace_cfg.get("onboarding") or {}).get("enabled"):
        onboarding_channel = ((ace_cfg.get("onboarding") or {}).get("channel_id")
                              or ensure_onboarding_channel(profile, ace_cfg, name_to_id))
        if onboarding_channel:
            ace_cfg.setdefault("onboarding", {})["channel_id"] = str(onboarding_channel)
            discord_block["free_response_channels"] = str(onboarding_channel)
            # bind the onboarding skill: threads inherit the parent channel's binding
            bindings = [b for b in (discord_block.get("channel_skill_bindings") or [])
                        if str(b.get("id")) != str(onboarding_channel)]
            bindings.append({"id": str(onboarding_channel), "skills": ["run-onboarding"]})
            discord_block["channel_skill_bindings"] = bindings

    # 2. home channel → profile .env (proactive output: cron results, notifications)
    home_name = str(ace_discord.get("home_channel") or DEFAULT_HOME_CHANNEL)
    home_id = name_to_id.get(home_name)
    if home_id:
        ensure_env(profile, {
            "DISCORD_HOME_CHANNEL": home_id,
            "DISCORD_HOME_CHANNEL_NAME": f"#{home_name}",
        })
    else:
        print(
            f"WARNING: home channel #{home_name} not found in the server — create it "
            "(or set discord.home_channel in the brand spec) and re-run.",
            file=sys.stderr,
        )

    # 3. channel-name → <#id> map → SOUL.md managed block (clickable channel mentions)
    soul_path = profile / "SOUL.md"
    soul_updated = False
    if soul_path.exists():
        soul = soul_path.read_text(encoding="utf-8")
        updated = upsert_channel_directory(soul, build_directory_block(name_to_id))
        if updated != soul:
            soul_path.write_text(updated, encoding="utf-8")
        soul_updated = True
    else:
        print(f"WARNING: {soul_path} not found — run setup.py first; skipping channel directory.",
              file=sys.stderr)

    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(json.dumps({
        "gateway": "mention-only (free_response_channels cleared; sweep cron covers the rest)",
        "swept_channels": {n: name_to_id[n] for n in sorted(free_response_names) if n in name_to_id},
        "missing": missing,
        "home_channel": {"name": home_name, "id": home_id},
        "onboarding_channel": onboarding_channel,
        "soul_channel_directory": soul_updated,
        "next": "restart the gateway to pick up the gateway config and home channel",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
