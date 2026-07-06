#!/usr/bin/env python3
"""Assign the brand's creator role(s) after onboarding data is collected.

Deterministic role assignment via the Discord API. Exits non-zero with a clear error on
ANY failure (missing role, missing permissions, hierarchy) — the calling skill must then
tell the creator the team's been looped in AND flag Slack. Never a silent failure: a
missing role blocks the creator from seeing brand channels.

Usage:
    python assign_role.py --user-id <discord_id> [--role Creator ...] [--profile-dir <dir>]
    (default roles: ace.onboarding.creator_roles from the profile config)
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
UA = "DiscordBot (https://github.com/michaeljajou/ascend-commerce-ace, 0.1)"


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


def request(token: str, path: str, method: str = "GET"):
    req = urllib.request.Request(
        f"{DISCORD_API}{path}",
        headers={"Authorization": f"Bot {token}", "User-Agent": UA},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body.strip() else {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--role", action="append", help="role name or id (repeatable); default: config")
    args = ap.parse_args(argv)
    profile = Path(args.profile_dir)

    import yaml

    config = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8")) or {}
    ace = config.get("ace") or {}
    guild_id = str((ace.get("discord") or {}).get("guild_id") or "")
    wanted = args.role or (ace.get("onboarding") or {}).get("creator_roles") or ["Creator"]

    token = bot_token(profile)
    if not token or not guild_id:
        print("ERROR: missing DISCORD_BOT_TOKEN or guild_id.", file=sys.stderr)
        return 1

    try:
        roles = request(token, f"/guilds/{guild_id}/roles")
        by_key = {r["name"].lower(): r["id"] for r in roles} | {r["id"]: r["id"] for r in roles}
        assigned, missing = [], []
        for want in wanted:
            rid = by_key.get(str(want).lower()) or by_key.get(str(want))
            if not rid:
                missing.append(want)
                continue
            request(token, f"/guilds/{guild_id}/members/{args.user_id}/roles/{rid}", method="PUT")
            assigned.append(want)
        if missing:
            print(f"ERROR: role(s) not found in this server: {missing} — create them or fix "
                  "ace.onboarding.creator_roles.", file=sys.stderr)
            return 1
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:200]
        print(f"ERROR: role assignment failed (HTTP {exc.code}): {detail} — likely the bot lacks "
              "Manage Roles or its role sits below the creator role.", file=sys.stderr)
        return 1

    print(json.dumps({"assigned": assigned, "user_id": args.user_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
