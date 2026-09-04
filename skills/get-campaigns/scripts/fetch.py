#!/usr/bin/env python3
"""Fetch the brand's ACTIVE campaigns/challenges live from its Discord channels.

Launch-by-posting convention: the team launches a campaign/challenge simply by
posting it in #campaigns / #challenges — the NEWEST post in each channel IS the
active one. #announcements is read too, as a MIXED feed: campaign notices (the
Growi sign-up link, date changes, weekly leaderboards) land there between unrelated
announcements, so its recent posts are returned for scanning, not ranked
newest-is-active.

Deterministic grounding only — no interpretation. Prints JSON: per launch channel
the `active` post (newest with text) and the `previous` ones; per mixed channel the
`recent` posts. Empty channel → active is null (the never-fabricate signal: escalate,
don't guess).

What counts as a team post: any human author, and any WEBHOOK post. Brands post
through webhooks — I Am Joy's "I Am Joy Brand" webhook posts every campaign and
announcement, text inside a rich embed — and Discord flags those as bot-authored.
Treating them as bots returned `active: null` for #campaigns with a live monthly
campaign on the board (2026-08-28 and 2026-09-03): Ace told two creators there was
no active campaign. Non-webhook bots (Ace's own replies) are still excluded. A
post's text is its content plus its rich embeds (title, description, fields,
footer); link-preview embeds are noise and skipped; image-only posts carry no
readable text and are skipped, but attachments on text posts are listed by URL.

Requires: the profile's channel_directory.json (exists after the gateway's first
Discord connect) and DISCORD_BOT_TOKEN (env, or read from the profile .env).

Usage:
    python3 fetch.py [--profile-dir <dir>] [--channels campaigns,challenges,announcements] [--limit 10]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DISCORD_API = "https://discord.com/api/v10"
DEFAULT_CHANNELS = "campaigns,challenges,announcements"
# Mixed feeds: many kinds of posts, so the newest one is not "the active campaign".
MIXED_CHANNELS = {"announcements"}
# Embed types Discord generates itself for links in the text (site previews) — never
# something the team wrote.
_PREVIEW_EMBED_TYPES = {"article", "link", "video", "image", "gifv"}


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


# Mirror of setup-brand/scripts/prep_server.channel_slug (canonical) — this script runs
# in the agent sandbox and must stay self-contained. Live servers decorate channel names
# ('🏁│campaigns'); config/spec carry plain names. Exact-name matching here burned an
# onboarding run's whole iteration budget ("none of the channels exist") and the
# budget-exhaustion fallback leaked raw model markup into the creator's welcome thread
# (I Am Joy, 2026-08-04).
_NAME_SEPARATORS = ("/", "│", "︱", "┃", "|")


def channel_slug(name: str) -> str:
    for sep in _NAME_SEPARATORS:
        if sep in name:
            name = name.rsplit(sep, 1)[1]
    name = name.strip().lstrip("#")
    while name and not name[0].isalnum():
        name = name[1:]
    return name.casefold()


def channel_ids(profile: Path, names: list[str]) -> tuple[dict[str, str], list[str]]:
    """Resolve channel names via the profile's channel_directory.json → (found, missing).
    Names are matched on slugs so decorated live names satisfy plain config names."""
    directory_path = profile / "channel_directory.json"
    if not directory_path.exists():
        raise FileNotFoundError(
            f"{directory_path} not found — run the gateway once so it connects to Discord "
            "and builds the channel directory."
        )
    directory = json.loads(directory_path.read_text(encoding="utf-8"))
    name_to_id = {
        channel_slug(c["name"]): c["id"]
        for c in directory.get("platforms", {}).get("discord", [])
        if c.get("type") == "channel" and c.get("name")
    }
    found = {n: name_to_id[channel_slug(n)] for n in names if channel_slug(n) in name_to_id}
    missing = [n for n in names if channel_slug(n) not in name_to_id]
    return found, missing


def fetch_messages(token: str, channel_id: str, limit: int) -> list[dict]:
    """GET the channel's most recent messages (Discord returns newest first)."""
    req = urllib.request.Request(
        f"{DISCORD_API}/channels/{channel_id}/messages?limit={limit}",
        headers={"Authorization": f"Bot {token}", "User-Agent": "DiscordBot (https://github.com/michaeljajou/ascend-commerce-ace, 0.1)"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def embed_text(embed: dict) -> str:
    """The readable text of a rich embed: title, description, `name: value` fields, footer."""
    if (embed.get("type") or "rich") in _PREVIEW_EMBED_TYPES:
        return ""
    parts = []
    if embed.get("title"):
        parts.append(str(embed["title"]).strip())
    if embed.get("description"):
        parts.append(str(embed["description"]).strip())
    for field in embed.get("fields") or []:
        name = str(field.get("name") or "").strip()
        value = str(field.get("value") or "").strip()
        if name and value:
            parts.append(f"{name}: {value}")
        elif name or value:
            parts.append(name or value)
    footer = (embed.get("footer") or {}).get("text")
    if footer:
        parts.append(str(footer).strip())
    return "\n".join(p for p in parts if p)


def post_text(message: dict) -> str:
    """Everything the team wrote in a post: its content plus its rich embeds."""
    parts = [(message.get("content") or "").strip()]
    parts += [embed_text(e) for e in message.get("embeds") or []]
    return "\n\n".join(p for p in parts if p).strip()


def is_team_post(message: dict) -> bool:
    """Humans and webhooks are the team; other bots (Ace's own replies) are not."""
    if message.get("webhook_id"):
        return True
    return not (message.get("author") or {}).get("bot")


def summarize(messages: list[dict], *, mode: str = "launch") -> dict:
    """Launch mode: newest text post = active, the rest = previous.
    Recent mode (mixed feeds): every text post, newest first, for the agent to scan.

    Ignores posts with no readable text (image-only) and non-webhook bot posts — Ace's
    own replies in the channel must never be mistaken for the campaign.
    """
    posts = []
    for m in messages:
        text = post_text(m)
        if not text or not is_team_post(m):
            continue
        post = {
            "posted_at": m.get("timestamp"),
            "author": (m.get("author") or {}).get("username"),
            "content": text,
        }
        urls = [a.get("url") for a in m.get("attachments") or [] if a.get("url")]
        if urls:
            post["attachments"] = urls
        posts.append(post)
    if mode == "recent":
        return {"recent": posts}
    return {"active": posts[0] if posts else None, "previous": posts[1:]}


NOTE = (
    "Launch channels (campaigns, challenges): the ACTIVE campaign/challenge is the newest post; "
    "`previous` is history only. Mixed feeds (announcements): `recent` posts are returned for "
    "scanning — campaign notices sit between unrelated announcements, and newest does not mean "
    "active. Answer only from these posts, as literally stated (dates, prizes, links); check a "
    "post's campaign dates against fetched_at before calling it running or ended. If nothing here "
    "covers the question, escalate — don't guess."
)


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
        mode = "recent" if channel_slug(name) in MIXED_CHANNELS else "launch"
        try:
            channels[name] = summarize(fetch_messages(token, cid, args.limit), mode=mode)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"ERROR: could not fetch #{name}: {exc}", file=sys.stderr)
            return 1

    print(json.dumps({
        "note": NOTE,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channels": channels,
        "missing_channels": missing,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
