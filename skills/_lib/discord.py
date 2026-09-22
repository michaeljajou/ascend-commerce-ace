"""Discord REST for the bundle's posting scripts: bot token lookup, channel-name
resolution against the gateway's directory, posting without pings, and "did this bot
already post here?".

stdlib only — these run inside the agent's code sandbox, which has no third-party
packages (see ``_lib/brand.py`` for the incident behind that rule).

Channel names: live servers decorate them ('📢│announcements', 'Brand / #campaigns')
while the spec and brand.json carry plain names, so everything matches on slugs. Exact
matching burned an onboarding run's whole iteration budget (I Am Joy, 2026-08-04) and
made weekly-reminders 404 silently for a month (I Am Joy, Aug–Sep 2026).
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DISCORD_API = "https://discord.com/api/v10"
# Cloudflare returns 403 (error 1010) to datacenter IPs unless the UA looks like a bot library.
USER_AGENT = "DiscordBot (https://github.com/michaeljajou/ascend-commerce-ace, 0.1)"
DISCORD_MAX_CONTENT = 2000
_NAME_SEPARATORS = ("/", "│", "︱", "┃", "|")


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


def channel_slug(name: str) -> str:
    """'📢│announcements' / 'Brand / #campaigns' / '#Community-Chat' → plain lower-case name."""
    for sep in _NAME_SEPARATORS:
        if sep in name:
            name = name.rsplit(sep, 1)[1]
    name = name.strip().lstrip("#")
    while name and not name[0].isalnum():
        name = name[1:]
    return name.casefold()


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
        channel_slug(c["name"]): str(c["id"])
        for c in directory.get("platforms", {}).get("discord", [])
        if c.get("type") == "channel" and c.get("name")
    }
    found = {n: name_to_id[channel_slug(n)] for n in names if channel_slug(n) in name_to_id}
    missing = [n for n in names if channel_slug(n) not in name_to_id]
    return found, missing


def _request(token: str, path: str, payload: dict | None = None):
    req = urllib.request.Request(
        f"{DISCORD_API}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                 "User-Agent": USER_AGENT},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_message(token: str, channel_id: str, text: str,
                 allowed_mentions: dict | None = None) -> dict:
    """POST a message. Default: no mention of any kind is expanded — an automated post
    never pings @everyone, a role, or a person. Returns Discord's message object."""
    payload = {"content": text, "allowed_mentions": allowed_mentions or {"parse": []}}
    return _request(token, f"/channels/{channel_id}/messages", payload)


def recent_own_post(token: str, channel_id: str, within_minutes: int = 60,
                    now: datetime | None = None) -> dict | None:
    """This bot's newest message in the channel if it is younger than the window, else None.
    The double-post guard for scripts an agent may retry."""
    me = str(_request(token, "/users/@me")["id"])
    messages = _request(token, f"/channels/{channel_id}/messages?limit=20")
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(minutes=within_minutes)
    for m in messages:                      # Discord returns newest first
        if str((m.get("author") or {}).get("id")) != me:
            continue
        posted_at = datetime.fromisoformat(m["timestamp"])
        return m if posted_at >= cutoff else None
    return None
