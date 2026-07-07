#!/usr/bin/env python3
"""Shared Slack-post CLI: brand-tagged, outbound-only escalation/digest delivery.

All brands escalate into ONE shared Slack channel (default #ace-escalations), so every
message is automatically prefixed with the brand tag `[<brand name>]` — the team must
always see which brand a post is about.

Outbound-only by design: uses the Slack Web API with SLACK_BOT_TOKEN alone. Brand
profiles must NOT get SLACK_APP_TOKEN (a second socket-mode gateway would steal events
from the operator's root gateway) — posting needs only the bot token in the profile
.env, which the operator copies there (or attaches via `<brand> setup`).

Usage:
    python slack_cli.py post --text "creator @x asked ... — needs team"     # to ace.slack_channel
    echo "long summary" | python slack_cli.py post --stdin
    python slack_cli.py post --channel "#other" --text "..."               # explicit override
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

SLACK_API = "https://slack.com/api/chat.postMessage"
DEFAULT_CHANNEL = "#ace-escalations"


def profile_dir() -> Path:
    """The profile root, from the bundle's data-dir contract (ACE_DATA_DIR = <profile>/ace)."""
    if data_dir := os.environ.get("ACE_DATA_DIR"):
        return Path(data_dir).parent
    return Path(os.environ.get("HERMES_HOME", "."))


def load_ace_config(profile: Path) -> dict:
    cfg_path = profile / "config.yaml"
    if not cfg_path.exists():
        return {}
    import yaml

    return (yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}).get("ace") or {}


def bot_token(profile: Path) -> str | None:
    """Prefer ACE_SLACK_BOT_TOKEN: naming it SLACK_BOT_TOKEN in a brand .env makes the
    Hermes gateway think the profile has a Slack platform and retry-connect forever
    (brands are outbound-only). The ACE_ prefix keeps Hermes blind to it."""
    for key in ("ACE_SLACK_BOT_TOKEN", "SLACK_BOT_TOKEN"):
        if tok := os.environ.get(key):
            return tok
    env_path = profile / ".env"
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        for key in ("ACE_SLACK_BOT_TOKEN=", "SLACK_BOT_TOKEN="):
            for line in lines:
                s = line.strip()
                if s.startswith(key):
                    return s.split("=", 1)[1].strip().strip("'\"") or None
    return None


def post_message(token: str, channel: str, text: str) -> dict:
    req = urllib.request.Request(
        SLACK_API,
        data=json.dumps({"channel": channel, "text": text}).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "ace-slack/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Post a brand-tagged message to the team Slack channel.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("post")
    p.add_argument("--text", help="message text (or use --stdin)")
    p.add_argument("--stdin", action="store_true", help="read message text from stdin")
    p.add_argument("--channel", help="override channel (default: ace.slack_channel from config)")
    args = ap.parse_args(argv)

    text = (sys.stdin.read() if args.stdin else args.text or "").strip()
    if not text:
        print("ERROR: empty message text.", file=sys.stderr)
        return 1

    profile = profile_dir()
    ace = load_ace_config(profile)
    channel = args.channel or ace.get("slack_channel") or DEFAULT_CHANNEL
    brand = ace.get("brand_name") or ace.get("brand_id")
    if brand:
        text = f"[{brand}] {text}"

    token = bot_token(profile)
    if not token:
        print("ERROR: SLACK_BOT_TOKEN not set and not found in the profile .env — the operator "
              "must add the bot token to this profile for Slack escalations.", file=sys.stderr)
        return 1

    result = post_message(token, channel, text)
    if not result.get("ok"):
        print(f"ERROR: Slack API refused the post: {result.get('error')} "
              f"(channel {channel} — is the bot invited to it?)", file=sys.stderr)
        return 1
    print(json.dumps({"posted": channel, "ts": result.get("ts"), "brand_tag": brand}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
