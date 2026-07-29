#!/usr/bin/env python3
"""Scripted server prep: create the standard roles and channels for a new brand server.

Born during the I Am Joy live run when the operator asked "can't the CLI do this?" —
and most of the server-prep checklist is indeed plain REST once the bot is invited with
Manage Roles + Manage Channels: create `Ascend Team` / `onboarded` / `creator`, create
#agent-ace and the brand's knowledge channels, and verify the Step-1 portal work
(privileged intents) from the application flags. What stays human, always: turning the
old greeter bot (Vaulty) off (another bot's config), choosing which people get
`Ascend Team`, and dragging new channels into categories (cosmetic).

Dry-run by default; `--apply` executes. Idempotent — a re-run creates nothing.

Usage (operator script — run with the Hermes venv, NOT the agent sandbox):
    python prep_server.py --profile-dir /opt/data/profiles/<brand> \
        --channels announcements community-chat our-products campaigns challenges how-to-level-up
    ... --apply            # actually create
    ... --guild-id <id>    # only needed if the bot is in more than one guild

Roles are created at the bottom of the role list — below the bot's top role — which is
exactly where they must sit for the bot to assign them later. A pre-existing role AT or
ABOVE the bot's top role is reported, not moved: Discord forbids the bot from managing
it, so a human must drag it below the bot's role by hand.
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

DEFAULT_ROLES = ["Ascend Team", "onboarded", "creator"]
TEXT_CHANNEL = 0

# Application flags: for each privileged intent Discord sets the plain bit once the bot
# is verified, or the *_LIMITED bit for unverified bots (<100 guilds) with the portal
# toggle on. Either bit means the intent works — new brand bots always start LIMITED.
GUILD_MEMBERS = (1 << 14) | (1 << 15)
MESSAGE_CONTENT = (1 << 18) | (1 << 19)


def discord(token: str, path: str, payload: dict | None = None, method: str | None = None):
    req = urllib.request.Request(
        f"{DISCORD_API}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                 "User-Agent": UA},
        method=method or ("POST" if payload is not None else "GET"),
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body.strip() else {}


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


def intent_summary(flags: int) -> dict:
    """The Step-1 portal toggles, read back from the application object."""
    return {"server_members": bool(flags & GUILD_MEMBERS),
            "message_content": bool(flags & MESSAGE_CONTENT)}


def plan_roles(existing: list[dict], wanted: list[str], bot_top_position: int) -> dict:
    """Which wanted roles to create, and which pre-existing ones the bot cannot manage.

    Name match is case-insensitive — operators type "ascend team" and Discord keeps it
    verbatim; a duplicate differing only in case would be worse than accepting theirs.
    """
    by_name = {r["name"].casefold(): r for r in existing}
    create, present, misplaced = [], [], []
    for name in wanted:
        role = by_name.get(name.casefold())
        if role is None:
            create.append(name)
            continue
        present.append(role["name"])
        if int(role.get("position", 0)) >= bot_top_position:
            misplaced.append(role["name"])       # at/above the bot: it can't assign this
    return {"create": create, "present": present, "misplaced": misplaced}


def plan_channels(existing: list[dict], wanted: list[str]) -> dict:
    """Which wanted TEXT channels to create. Voice/category namesakes don't count."""
    have = {c["name"].casefold() for c in existing if c.get("type") == TEXT_CHANNEL}
    names = [w.lstrip("#") for w in wanted]
    return {"create": [n for n in names if n.casefold() not in have],
            "present": [n for n in names if n.casefold() in have]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create the standard roles/channels for a brand server.")
    ap.add_argument("--profile-dir", required=True)
    ap.add_argument("--guild-id", help="required only when the bot is in several guilds")
    ap.add_argument("--roles", nargs="*", default=DEFAULT_ROLES)
    ap.add_argument("--channels", nargs="*", default=[],
                    help="brand channels to ensure exist (agent-ace is always included)")
    ap.add_argument("--apply", action="store_true", help="execute (default: dry run)")
    args = ap.parse_args(argv)

    profile = Path(args.profile_dir)
    token = bot_token(profile)
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not set and not in the profile .env.", file=sys.stderr)
        return 1

    app = discord(token, "/applications/@me")
    intents = intent_summary(int(app.get("flags", 0)))
    guilds = discord(token, "/users/@me/guilds")
    if args.guild_id:
        guild = next((g for g in guilds if g["id"] == args.guild_id), None)
        if guild is None:
            print(f"ERROR: bot is not in guild {args.guild_id}.", file=sys.stderr)
            return 1
    elif len(guilds) == 1:
        guild = guilds[0]
    else:
        print(f"ERROR: bot is in {len(guilds)} guilds — pass --guild-id. "
              + ", ".join(f"{g['name']}={g['id']}" for g in guilds), file=sys.stderr)
        return 1
    gid = guild["id"]

    me = discord(token, "/users/@me")
    member = discord(token, f"/guilds/{gid}/members/{me['id']}")
    roles = discord(token, f"/guilds/{gid}/roles")
    positions = {r["id"]: int(r.get("position", 0)) for r in roles}
    bot_top = max((positions.get(rid, 0) for rid in member.get("roles", [])), default=0)

    role_plan = plan_roles(roles, args.roles, bot_top)
    channels = discord(token, f"/guilds/{gid}/channels")
    chan_plan = plan_channels(channels, ["agent-ace", *args.channels])

    errors = []
    if args.apply:
        for name in role_plan["create"]:
            try:
                discord(token, f"/guilds/{gid}/roles", {"name": name, "permissions": "0"})
            except urllib.error.HTTPError as e:
                errors.append(f"role {name!r}: HTTP {e.code} — does the bot have Manage Roles?")
        for name in chan_plan["create"]:
            try:
                discord(token, f"/guilds/{gid}/channels", {"name": name, "type": TEXT_CHANNEL})
            except urllib.error.HTTPError as e:
                errors.append(f"channel #{name}: HTTP {e.code} — does the bot have Manage Channels?")

    human_residue = [
        "turn the old greeter bot's (Vaulty) join handling OFF — its config, not ours",
        "assign 'Ascend Team' to every human team member (Server Settings → Members)",
        "drag newly created channels into categories if wanted (cosmetic)",
    ]
    for name in role_plan["misplaced"]:
        human_residue.append(f"drag role {name!r} BELOW the bot's role — it sits at/above "
                             "the bot, so the bot cannot assign it")

    print(json.dumps({
        "mode": "applied" if args.apply else "dry-run",
        "guild": {"id": gid, "name": guild.get("name")},
        "intents": intents,
        "roles": role_plan,
        "channels": chan_plan,
        "errors": errors,
        "human_residue": human_residue,
    }, indent=2))
    if not (intents["server_members"] and intents["message_content"]):
        print("WARNING: a privileged intent is OFF in the Developer Portal — onboarding "
              "join-polls and message reading will fail. Fix before going further.",
              file=sys.stderr)
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
