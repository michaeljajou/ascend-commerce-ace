#!/usr/bin/env python3
"""Assign the brand's creator role(s) after onboarding data is collected.

Deterministic role assignment via the Discord API. Exits non-zero with a clear error on
ANY failure (missing role, missing permissions, hierarchy) — the caller must then tell the
creator the team's been looped in AND flag Slack. Never a silent failure: a missing role
blocks the creator from seeing brand channels.

Normally you do NOT run this by hand — ``onboarding.py complete`` calls ``assign()`` for
you, resolving the Discord ID from the store. The CLI exists for operator repair work:

    python assign_role.py --handle @ava                  # id resolved from the store
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


def assign(user_id: str, roles: list[str] | None = None,
           profile: Path | None = None) -> dict:
    """Grant the brand's creator roles to one member.

    Returns ``{"ok": True, "assigned": [...]}`` or ``{"ok": False, "error": "<one line>"}``.
    Never raises: the caller (``onboarding.py complete``) turns a failure into a Slack
    alert plus a creator-facing "the team will finish this" message, and that path must
    not itself blow up.
    """
    profile = profile or Path(os.environ.get("HERMES_HOME", "."))
    if not user_id:
        return {"ok": False, "error": "no Discord ID on record for this creator — the "
                                      "onboarding tick stores it at join time."}

    import yaml

    try:
        config = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8")) or {}
    except OSError as exc:
        return {"ok": False, "error": f"cannot read {profile}/config.yaml ({exc})"}
    ace = config.get("ace") or {}
    guild_id = str((ace.get("discord") or {}).get("guild_id") or "")
    wanted = roles or (ace.get("onboarding") or {}).get("creator_roles") or ["Creator"]

    token = bot_token(profile)
    if not token or not guild_id:
        return {"ok": False, "error": "missing DISCORD_BOT_TOKEN or ace.discord.guild_id."}

    try:
        guild_roles = request(token, f"/guilds/{guild_id}/roles")
        by_key = ({r["name"].lower(): r["id"] for r in guild_roles}
                  | {r["id"]: r["id"] for r in guild_roles})
        assigned, missing = [], []
        for want in wanted:
            rid = by_key.get(str(want).lower()) or by_key.get(str(want))
            if not rid:
                missing.append(want)
                continue
            request(token, f"/guilds/{guild_id}/members/{user_id}/roles/{rid}", method="PUT")
            assigned.append(want)
        if missing:
            return {"ok": False, "assigned": assigned,
                    "error": f"role(s) not found in this server: {missing} — create them "
                             "or fix ace.onboarding.creator_roles."}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:200]
        return {"ok": False, "error": f"HTTP {exc.code}: {detail} — likely the bot lacks "
                                      "Manage Roles, or its role sits below the creator role."}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": f"Discord unreachable ({exc})"}

    return {"ok": True, "assigned": assigned, "user_id": user_id}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    ap.add_argument("--user-id", help="Discord snowflake; omit and pass --handle instead")
    ap.add_argument("--handle", help="@username — resolves the Discord ID from the store")
    ap.add_argument("--role", action="append", help="role name or id (repeatable); default: config")
    args = ap.parse_args(argv)

    user_id = args.user_id
    if not user_id and args.handle:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills
        from _lib import store

        row = store.get_onboarding(store.connect(), args.handle) or {}
        user_id = row.get("discord_id")
    if not user_id:
        print("ERROR: pass --user-id, or --handle for a creator already in the store.",
              file=sys.stderr)
        return 1

    result = assign(user_id, args.role, Path(args.profile_dir))
    if not result["ok"]:
        print(f"ERROR: role assignment failed: {result['error']}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
