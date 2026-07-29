#!/usr/bin/env python3
"""Scripted server prep: create the standard roles and channels for a new brand server.

Born during the I Am Joy live run when the operator asked "can't the CLI do this?" —
and most of the server-prep checklist is indeed plain REST once the bot is invited with
Manage Roles + Manage Channels: create `Ascend Team` / `onboarded` / `creator`, create
#agent-ace and the brand's knowledge channels, verify the Step-1 portal work
(privileged intents) from the application flags, audit the bot's OWN guild permissions
(printing the re-invite URL that fixes any gap — a bot can't self-escalate), set the
bot's server nickname, and set the canonical Ace avatar from the repo asset
(`--avatar-file assets/ace-avatar.png`; `--avatar-from-profile` copies another bot's
instead). What stays human, always: creating the application, the two
privileged-intent toggles, the invite click, turning the old greeter bot (Vaulty) off
(another bot's config), and choosing which people get `Ascend Team`.

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
import base64
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
ADMINISTRATOR = 1 << 3

# Everything Ace needs at guild level: run the channels/threads/roles it manages, and
# nothing more. These bits double as the invite URL — one source of truth, so the audit
# and the fix can never disagree.
PERMS = {
    "view_channel": 1 << 10, "send_messages": 1 << 11, "embed_links": 1 << 14,
    "read_message_history": 1 << 16, "mention_everyone": 1 << 17, "add_reactions": 1 << 6,
    "manage_channels": 1 << 4, "manage_roles": 1 << 28, "manage_threads": 1 << 34,
    "create_private_threads": 1 << 36, "send_messages_in_threads": 1 << 38,
    "change_nickname": 1 << 26,
}

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


def missing_permissions(roles: list[dict], member_role_ids: list[str], guild_id: str) -> list[str]:
    """Guild-level audit of the bot's OWN permissions (union of its roles + @everyone).

    A bot cannot grant itself anything — Discord forbids self-escalation — so anything
    missing here is fixed by re-opening the invite URL (re-authorizing updates the
    integration role in place; nobody gets kicked). Channel overwrites are out of scope:
    gate_channels owns those.
    """
    perms = 0
    ids = set(member_role_ids) | {guild_id}          # the @everyone base always applies
    for r in roles:
        if r["id"] in ids:
            perms |= int(r.get("permissions", 0))
    if perms & ADMINISTRATOR:
        return []
    return [name for name, bit in PERMS.items() if not perms & bit]


def invite_url(app_id: str) -> str:
    bits = 0
    for b in PERMS.values():
        bits |= b
    return f"https://discord.com/oauth2/authorize?client_id={app_id}&scope=bot&permissions={bits}"


def file_data_uri(path: Path) -> str:
    """A local image as a data URI — the canonical Ace face lives in the repo at
    assets/ace-avatar.png, so every brand bot gets it from git, not from hoping some
    other bot already wears it."""
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif"}.get(path.suffix.lstrip(".").lower(), "image/png")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def avatar_data_uri(token: str) -> str | None:
    """The bot's current avatar as a data URI — lets a new brand bot copy the canonical
    Ace look from an existing brand's bot, so every server shows the same face."""
    me = discord(token, "/users/@me")
    h = me.get("avatar")
    if not h:
        return None
    ext, mime = ("gif", "image/gif") if h.startswith("a_") else ("png", "image/png")
    req = urllib.request.Request(
        f"https://cdn.discordapp.com/avatars/{me['id']}/{h}.{ext}?size=512",
        headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return f"data:{mime};base64,{base64.b64encode(resp.read()).decode('ascii')}"


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
    ap.add_argument("--nick", default="Ace",
                    help="server nickname for the bot (pass '' to leave as-is)")
    ap.add_argument("--avatar-file",
                    help="image file to set as the bot's avatar if it has none yet "
                         "(canonical: <repo>/assets/ace-avatar.png)")
    ap.add_argument("--avatar-from-profile",
                    help="profile dir of an existing brand — copy its bot's avatar if "
                         "this bot has none yet (fallback when no --avatar-file)")
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

    missing_perms = missing_permissions(roles, member.get("roles", []), gid)
    role_plan = plan_roles(roles, args.roles, bot_top)
    channels = discord(token, f"/guilds/{gid}/channels")
    chan_plan = plan_channels(channels, ["agent-ace", *args.channels])

    # Look: nickname + avatar. The avatar is copied from an existing brand's bot only
    # when this bot has none — a deliberately-set custom face is never clobbered.
    want_nick = args.nick if args.nick and member.get("nick") != args.nick else None
    want_avatar = None
    if not me.get("avatar"):
        if args.avatar_file:
            want_avatar = file_data_uri(Path(args.avatar_file))
        elif args.avatar_from_profile:
            src = bot_token(Path(args.avatar_from_profile))
            want_avatar = avatar_data_uri(src) if src else None

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
        if want_nick:
            try:
                discord(token, f"/guilds/{gid}/members/@me", {"nick": want_nick}, method="PATCH")
            except urllib.error.HTTPError as e:
                errors.append(f"nickname: HTTP {e.code} — needs the change_nickname permission")
        if want_avatar:
            try:
                discord(token, "/users/@me", {"avatar": want_avatar}, method="PATCH")
            except urllib.error.HTTPError as e:
                errors.append(f"avatar: HTTP {e.code} (avatar changes are rate-limited — "
                              "retry in a few minutes)")

    human_residue = [
        "turn the old greeter bot's (Vaulty) join handling OFF — its config, not ours",
        "assign 'Ascend Team' to every human team member (Server Settings → Members)",
        "drag newly created channels into categories if wanted (cosmetic)",
    ]
    for name in role_plan["misplaced"]:
        human_residue.append(f"drag role {name!r} BELOW the bot's role — it sits at/above "
                             "the bot, so the bot cannot assign it")
    if missing_perms:
        human_residue.append("bot permissions incomplete — re-open the invite URL below "
                             "(re-authorizing updates them in place, nobody is kicked)")

    print(json.dumps({
        "mode": "applied" if args.apply else "dry-run",
        "guild": {"id": gid, "name": guild.get("name")},
        "bot": {"username": me.get("username"), "nick": member.get("nick"),
                "set_nick": want_nick, "set_avatar": bool(want_avatar),
                "has_avatar": bool(me.get("avatar"))},
        "intents": intents,
        "permissions": {"missing": missing_perms,
                        "invite_url": invite_url(str(app.get("id", me.get("id"))))},
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
    if missing_perms:
        print("WARNING: the bot lacks guild permissions it needs — open the invite_url "
              "from the summary to re-grant, then re-run.", file=sys.stderr)
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
