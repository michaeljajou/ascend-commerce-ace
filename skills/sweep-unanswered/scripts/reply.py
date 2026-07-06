#!/usr/bin/env python3
"""Post Ace's reply to a swept message (deterministic delivery, no toolset needed).

Replies in-channel with a message_reference so Discord shows it as a reply to the
creator's message. Safe mentions only (no @everyone/@role pings).

Usage:
    python reply.py --channel-id <id> --reply-to <message_id> --text "<the reply>"
    echo "<the reply>" | python reply.py --channel-id <id> --reply-to <message_id> --stdin
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

DISCORD_API = "https://discord.com/api/v10"


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


def post_reply(token: str, channel_id: str, text: str, reply_to: str | None) -> dict:
    payload: dict = {
        "content": text,
        "allowed_mentions": {"parse": ["users"]},  # never ping @everyone/@here/roles
    }
    if reply_to:
        payload["message_reference"] = {"message_id": reply_to, "fail_if_not_exists": False}
    req = urllib.request.Request(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                 "User-Agent": "ace-reply/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    ap.add_argument("--channel-id", required=True)
    ap.add_argument("--reply-to", help="message id to reply to (recommended)")
    ap.add_argument("--text", help="reply text (or use --stdin)")
    ap.add_argument("--stdin", action="store_true", help="read reply text from stdin")
    args = ap.parse_args(argv)

    text = (sys.stdin.read() if args.stdin else args.text or "").strip()
    if not text:
        print("ERROR: empty reply text.", file=sys.stderr)
        return 1
    token = bot_token(Path(args.profile_dir))
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not set and not found in the profile .env.", file=sys.stderr)
        return 1

    sent = post_reply(token, args.channel_id, text, args.reply_to)
    print(json.dumps({"sent": sent.get("id"), "channel_id": args.channel_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
