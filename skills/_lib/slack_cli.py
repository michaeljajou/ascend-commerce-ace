#!/usr/bin/env python3
"""Shared Slack-post CLI: brand-tagged, outbound-only escalation/digest delivery.

All brands escalate into ONE shared Slack channel (default #ace-escalations), so every
message is automatically prefixed with the brand tag `[<brand name>]` — the team must
always see which brand a post is about.

Channel contract (team request, 2026-10-06): #ace-escalations carries ONLY posts that need
the team to act — a creator question Ace could not ground, a creative-strategist request, a
moderation notice, a creator locked out by a failed role assignment. The daily digest goes
to its own channel (`--purpose reporting` → ``ace.digest_channel``, default #ace-digests);
signup cards go to the onboarding data channel. Informational "stuck"/"inactive" notices
were removed outright rather than rerouted.

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
import re
import sys
import urllib.request
from pathlib import Path

SLACK_API = "https://slack.com/api/chat.postMessage"
DEFAULT_CHANNEL = "#ace-escalations"
DEFAULT_DIGEST_CHANNEL = "#ace-digests"     # the daily digest never lands among escalations
PURPOSE_FEATURE = {
    "support": "general_qa",
    "moderation": "moderation",
    "announcements": "announcements",
    "engagement": "engagement",
    "reporting": "reporting",
}

# --- Slack formatting -------------------------------------------------------------------
# Agent-composed text arrives in Discord/GitHub flavor: **bold**, ### headers, and raw
# Discord channel tags like <#1522268317321138176>. Slack renders none of that — the team
# saw literal asterisks and an unclickable snowflake (QA, 2026-07-23). The agent supplies
# words; formatting is mechanical, so it happens here, at the one door every brand-tagged
# Slack post walks through. Proper mrkdwn passes through untouched (idempotent): single
# *bold*, _italics_, <https://url|label> links, and Slack's own <#C…> refs are never
# matched — the Discord-tag regex requires an all-digit snowflake.
_HEADER_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_UNDERLINE_RE = re.compile(r"__(.+?)__", re.DOTALL)
_STRIKE_RE = re.compile(r"~~(.+?)~~", re.DOTALL)
_DISCORD_CHANNEL_RE = re.compile(r"<#(\d{15,})>")


def _discord_channel_names(profile: Path) -> dict:
    """id → name from the gateway's channel_directory.json; {} when unavailable."""
    try:
        raw = json.loads((profile / "channel_directory.json").read_text(encoding="utf-8"))
        # Live directories carry display names ("Test Brand / #community-chat"); Discord
        # channel names can't contain "/", so the last segment is always the channel.
        return {c.get("id"): (c.get("name") or "").split("/")[-1].strip().lstrip("#")
                for c in (raw.get("platforms") or {}).get("discord") or []
                if c.get("id") and c.get("name")}
    except (OSError, ValueError):
        return {}


def slackify(text: str, profile: Path | None = None) -> str:
    """Translate Discord/GitHub markdown to Slack mrkdwn; resolve Discord channel tags."""
    names = _discord_channel_names(profile or profile_dir())
    text = _HEADER_RE.sub(lambda m: "*" + m.group(1).replace("**", "") + "*", text)
    text = _BOLD_RE.sub(r"*\1*", text)
    text = _UNDERLINE_RE.sub(r"_\1_", text)
    text = _STRIKE_RE.sub(r"~\1~", text)
    return _DISCORD_CHANNEL_RE.sub(lambda m: f"#{names.get(m.group(1), m.group(1))}", text)


def _brand():
    """Import the config loader whether we're `_lib.slack_cli` or a directly-run script.

    Skills invoke this file both ways: `from _lib import slack_cli` inside other scripts,
    and `python _lib/slack_cli.py post ...` from a SKILL.md. A plain relative import works
    only for the first.
    """
    try:
        from . import brand           # imported as part of the _lib package
    except ImportError:               # run as a top-level script
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from _lib import brand
    return brand


def profile_dir() -> Path:
    """The profile root, from the bundle's data-dir contract (ACE_DATA_DIR = <profile>/ace)."""
    return _brand().profile_dir()


def load_ace_config(profile: Path) -> dict:
    """Via the PyYAML-free loader — the agent's sandbox has no third-party packages."""
    return _brand().config(profile)


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
    p.add_argument("--channel", help="override channel (default: ace.slack_channel from config; "
                                     "ace.digest_channel for --purpose reporting)")
    p.add_argument("--purpose", choices=(*PURPOSE_FEATURE, "onboarding"), default="support")
    args = ap.parse_args(argv)

    text = (sys.stdin.read() if args.stdin else args.text or "").strip()
    if not text:
        print("ERROR: empty message text.", file=sys.stderr)
        return 1

    profile = profile_dir()
    ace = load_ace_config(profile)
    if args.purpose == "reporting":
        channel = args.channel or ace.get("digest_channel") or DEFAULT_DIGEST_CHANNEL
    else:
        channel = args.channel or ace.get("slack_channel") or DEFAULT_CHANNEL
    brand_module = _brand()
    try:
        policy = brand_module.load_policy(profile)
    except brand_module.PolicyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if feature := PURPOSE_FEATURE.get(args.purpose):
        if not policy[feature]:
            print(json.dumps({"disabled": feature}))
            return 0
    else:
        onboarding = ace.get("onboarding") or {}
        # A brand with general Q&A posts what it always posted: the sidecar read here can
        # lag a switch flipped in config.yaml by hand. Only a restricted profile, always
        # activated through setup, is held to the switch.
        if not policy["general_qa"] and not onboarding.get("enabled"):
            print("ERROR: onboarding is disabled for this profile.", file=sys.stderr)
            return 1
        allowed_channels = {
            value for value in (
                onboarding.get("data_channel"), onboarding.get("slack_channel"),
                ace.get("slack_channel"),
            ) if value
        }
        if channel not in allowed_channels:
            print("ERROR: onboarding posts must target a configured onboarding Slack channel.",
                  file=sys.stderr)
            return 1
    text = slackify(text, profile)              # Discord/GitHub markdown → Slack mrkdwn
    brand = ace.get("brand_name") or ace.get("brand_id")
    if brand:
        text = f"[{brand}] {text}"

    token = bot_token(profile)
    if not token:
        print("ERROR: SLACK_BOT_TOKEN not set and not found in the profile .env — the operator "
              "must add the bot token to this profile for Slack escalations.", file=sys.stderr)
        return 1

    import urllib.error

    try:
        result = post_message(token, channel, text)
    except (urllib.error.URLError, TimeoutError) as exc:
        # Clean failure, no traceback — callers (cron agents) must see a plain error
        # they can report, never a stack dump they might swallow.
        print(f"ERROR: could not reach Slack: {exc}", file=sys.stderr)
        return 1
    if not result.get("ok"):
        print(f"ERROR: Slack API refused the post: {result.get('error')} "
              f"(channel {channel} — is the bot invited to it?)", file=sys.stderr)
        return 1
    print(json.dumps({"posted": channel, "ts": result.get("ts"), "brand_tag": brand}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
