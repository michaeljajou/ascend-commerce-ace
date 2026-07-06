#!/usr/bin/env python3
"""Fetch the brand's ACTIVE campaigns/challenges live from its Discord channels.

Launch-by-posting convention: the team launches a campaign/challenge simply by
posting it in #campaigns / #challenges — the NEWEST post in each channel IS the
active one. This script reads those channels through the Discord API so Ace is
always grounded in what's actually running, with no manual knowledge.yaml update
per launch.

Deterministic grounding only — no interpretation. Prints JSON: per channel the
`active` post (newest with text content) and the `previous` ones. Empty channel
→ active is null (the never-fabricate signal: escalate, don't guess).

Requires: the profile's channel_directory.json (exists after the gateway's first
Discord connect) and DISCORD_BOT_TOKEN (env, or read from the profile .env).

Usage:
    python fetch.py [--profile-dir <dir>] [--channels campaigns,challenges] [--limit 10]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DISCORD_API = "https://discord.com/api/v10"
DEFAULT_CHANNELS = "campaigns,challenges"


def bot_token(profile: Path) -> str | None:
    """DISCORD_BOT_TOKEN from the environment, else the profile's .env."""
    if tok := os.environ.get("DISCORD_BOT_TOKEN"):
        return tok
    env_path = profile / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("DISCORD_BOT_TOKEN="):
                return s.split("=", 1)[1].strip().strip("'\"") or None
    return None


def channel_ids(profile: Path, names: list[str]) -> tuple[dict[str, str], list[str]]:
    """Resolve channel names via the profile's channel_directory.json → (found, missing)."""
    directory_path = profile / "channel_directory.json"
    if not directory_path.exists():
        raise FileNotFoundError(
            f"{directory_path} not found — run the gateway once so it connects to Discord "
            "and builds the channel directory."
        )
    directory = json.loads(directory_path.read_text(encoding="utf-8"))
    name_to_id = {
        c["name"]: c["id"]
        for c in directory.get("platforms", {}).get("discord", [])
        if c.get("type") == "channel"
    }
    found = {n: name_to_id[n] for n in names if n in name_to_id}
    missing = [n for n in names if n not in name_to_id]
    return found, missing


def fetch_messages(token: str, channel_id: str, limit: int) -> list[dict]:
    """GET the channel's most recent messages (Discord returns newest first)."""
    req = urllib.request.Request(
        f"{DISCORD_API}/channels/{channel_id}/messages?limit={limit}",
        headers={"Authorization": f"Bot {token}", "User-Agent": "DiscordBot (https://github.com/michaeljajou/ascend-commerce-ace, 0.1)"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def summarize(messages: list[dict]) -> dict:
    """Newest text post = active; the rest = previous.

    Ignores empty/attachment-only posts AND bot-authored ones — Ace's own replies
    (or any other bot) in the channel must never be mistaken for the campaign.
    """
    posts = []
    for m in messages:
        content = (m.get("content") or "").strip()
        if not content or (m.get("author") or {}).get("bot"):
            continue
        posts.append({
            "posted_at": m.get("timestamp"),
            "author": (m.get("author") or {}).get("username"),
            "content": content,
        })
    return {"active": posts[0] if posts else None, "previous": posts[1:]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # When a profile runs, Hermes sets HERMES_HOME to that profile's dir — the right default here.
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    ap.add_argument("--channels", default=DEFAULT_CHANNELS,
                    help=f"comma-separated channel names (default: {DEFAULT_CHANNELS})")
    ap.add_argument("--limit", type=int, default=10, help="messages to fetch per channel")
    args = ap.parse_args(argv)

    profile = Path(args.profile_dir)
    names = [n.strip().lstrip("#") for n in args.channels.split(",") if n.strip()]

    token = bot_token(profile)
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not set and not found in the profile .env.", file=sys.stderr)
        return 1
    try:
        found, missing = channel_ids(profile, names)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not found:
        print(f"ERROR: none of the channels {names} exist in this server.", file=sys.stderr)
        return 1

    channels = {}
    for name, cid in found.items():
        try:
            channels[name] = summarize(fetch_messages(token, cid, args.limit))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"ERROR: could not fetch #{name}: {exc}", file=sys.stderr)
            return 1

    print(json.dumps({
        "note": "The ACTIVE campaign/challenge is the newest post in each channel. "
                "Answer only from these posts; if active is null, escalate — don't guess.",
        "channels": channels,
        "missing_channels": missing,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
