#!/usr/bin/env python3
"""Post Ace's reply to a swept message (deterministic delivery, no toolset needed).

Replies in-channel with a message_reference so Discord shows it as a reply to the
creator's message, pings that creator (replied_user), and with --mention makes sure
their <@id> tag is in the text. Safe mentions only (no @everyone/@role pings).

Hand the text over on STDIN inside a quoted heredoc — never through --text "..." in a
shell. Both I Am Joy sweep replies of 2026-08-28 and 2026-09-03 went through --text in
the terminal tool: bash kept `\\n` as two literal characters and expanded `$5` in "$50"
to nothing, so creators read "\\n\\n" mid-message and "a chance to win 0!". A quoted
heredoc (<<'EOF') does no expansion at all.

Usage:
    python3 reply.py --channel-id <id> --reply-to <message_id> --mention <user_id> --stdin <<'EOF'
    Hey <@user_id> 👋 ...
    EOF
    python3 reply.py --channel-id <id> --reply-to <message_id> --text "<reply>"   # avoid: shell mangles $ and \\n
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
DISCORD_MAX_CONTENT = 2000


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


def clean_text(text: str) -> str:
    """Repair what a shell did to the text: a literal backslash-n is the newline the
    agent meant (bash keeps `\\n` verbatim inside double quotes)."""
    return text.replace("\\r\\n", "\n").replace("\\n", "\n").strip()


def with_mention(text: str, user_id: str | None) -> str:
    """Guarantee the creator's tag is in the message; keep the agent's own placement."""
    if not user_id:
        return text
    if f"<@{user_id}>" in text or f"<@!{user_id}>" in text:
        return text
    return f"<@{user_id}> {text}"


def post_reply(token: str, channel_id: str, text: str, reply_to: str | None) -> dict:
    payload: dict = {
        "content": text,
        # never ping @everyone/@here/roles; DO ping the creator being replied to —
        # Discord defaults replied_user to false once allowed_mentions is supplied
        "allowed_mentions": {"parse": ["users"], "replied_user": True},
    }
    if reply_to:
        payload["message_reference"] = {"message_id": reply_to, "fail_if_not_exists": False}
    req = urllib.request.Request(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                 "User-Agent": "DiscordBot (https://github.com/michaeljajou/ascend-commerce-ace, 0.1)"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    ap.add_argument("--channel-id", required=True)
    ap.add_argument("--reply-to", help="message id to reply to (recommended)")
    ap.add_argument("--mention", help="the creator's Discord user id — their <@id> tag goes in the text")
    ap.add_argument("--text", help="reply text (prefer --stdin with a quoted heredoc)")
    ap.add_argument("--stdin", action="store_true", help="read reply text from stdin")
    args = ap.parse_args(argv)

    text = clean_text(sys.stdin.read() if args.stdin else args.text or "")
    if not text:
        print("ERROR: empty reply text.", file=sys.stderr)
        return 1
    text = with_mention(text, args.mention)
    if len(text) > DISCORD_MAX_CONTENT:
        print(f"ERROR: reply is {len(text)} characters; Discord allows {DISCORD_MAX_CONTENT}. "
              "Shorten it.", file=sys.stderr)
        return 1
    token = bot_token(Path(args.profile_dir))
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not set and not found in the profile .env.", file=sys.stderr)
        return 1

    try:
        sent = post_reply(token, args.channel_id, text, args.reply_to)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        print(f"ERROR: Discord rejected the reply ({exc.code}): {body}", file=sys.stderr)
        return 1
    print(json.dumps({"sent": sent.get("id"), "channel_id": args.channel_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
