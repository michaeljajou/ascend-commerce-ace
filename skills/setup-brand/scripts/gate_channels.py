#!/usr/bin/env python3
"""Lock the server until onboarding is done (the Vaulty gate), Discord-natively.

Goal: a brand-new member can see ONLY the onboarding channel. The moment Ace assigns
their `onboarded`/`creator` roles at the end of onboarding, every public channel opens.

How — the gate lives on the @everyone BASE ROLE, because Discord has no real
permission inheritance:
  1. @everyone loses View Channels server-wide. Category overwrites do NOT cascade to
     unsynced children — QA 2026-07-23: eleven channels with no overwrite of their own
     fell back to the base role and were fully visible to a fresh join. The base role
     is the only switch that covers every channel, including ones an operator creates
     next month. Fail-closed.
  2. The creator roles, staff role, and Ace's own role each GAIN View Channels
     server-wide, so role-holders (and the bot) see everything the instant the role
     lands. Grants are applied BEFORE the @everyone removal, and the removal aborts
     unless Ace's own sight is guaranteed — the gate can never blind the bot.
  3. The onboarding channel keeps an explicit @everyone ALLOW overwrite — a channel
     overwrite beats the missing base permission — so that one door stays open.

Category overwrites (deny @everyone / allow creators+staff+bot) are still written:
they preserve the narrower Paid Collab-style privacy and keep intent visible in the
Discord UI, but the base role is what actually gates.

No holding role assigned on join — that would leave a window where a fast creator
sees the whole server before the bot reacts; role/permission edits apply instantly.

Safe by default: prints the plan and changes NOTHING without --apply.

Usage:
    python gate_channels.py --profile-dir <dir>            # dry run (default)
    python gate_channels.py --profile-dir <dir> --apply
    python gate_channels.py --profile-dir <dir> --apply --open   # undo the gate
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
VIEW_CHANNEL = 1 << 10
ADMINISTRATOR = 1 << 3

ROLE, MEMBER = 0, 1  # permission-overwrite types


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


def home_channel_id(profile: Path) -> str | None:
    """The brand's #agent-ace ops channel (resolve_channels writes its id to .env).

    Team-facing: cron output and notifications land there, so the gate gives it
    staff+bot overwrites WITHOUT the creator-role allows — an onboarded creator should
    see the community, not Ace's ops feed (I Am Joy live run, 2026-08-04)."""
    env_path = profile / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("DISCORD_HOME_CHANNEL="):
                return s.split("=", 1)[1].strip().strip("'\"") or None
    return None


def is_already_private(channel: dict, guild_id: str, creator_role_ids: list[str]) -> bool:
    """True when a place is deliberately locked down TIGHTER than the gate: @everyone
    is denied and creators are not allowed (e.g. a Paid Collab category holding private
    1:1 channels). The gate exists to hide public channels from un-onboarded members —
    it must never WIDEN access, so these are left completely alone."""
    ows = {o["id"]: o for o in channel.get("permission_overwrites", [])}
    if not int(ows.get(guild_id, {}).get("deny", 0)) & VIEW_CHANNEL:
        return False
    return not any(int(ows.get(rid, {}).get("allow", 0)) & VIEW_CHANNEL
                   for rid in creator_role_ids)


def gate_targets(channels: list[dict], onboarding_id: str, *, guild_id: str = "",
                 creator_role_ids: list[str] | None = None) -> list[dict]:
    """What to actually write to: CATEGORIES plus channels that have no category.

    Discord channels inherit their category's overwrites, so gating the category is
    both sufficient and the only thing that reliably works — writing redundant
    per-channel overwrites is what produced a screen of harmless 403s in QA. The
    onboarding channel is always included so its door stays explicitly open, and
    already-private places are excluded so the gate can only ever narrow access.
    """
    out = []
    for c in channels:
        if c["id"] == onboarding_id:
            out.append(c)
            continue
        if c.get("type") != 4 and c.get("parent_id"):
            continue                                   # child: inherits its category
        if guild_id and creator_role_ids and is_already_private(c, guild_id, creator_role_ids):
            continue                                   # private on purpose — don't touch
        out.append(c)
    return out


def leaky_channels(channels: list[dict], guild_id: str, onboarding_id: str) -> list[dict]:
    """Children whose OWN @everyone overwrite re-allows View Channel — these defeat a
    gated category, so the operator has to know about them."""
    out = []
    for c in channels:
        if c["id"] == onboarding_id or not c.get("parent_id"):
            continue
        for o in c.get("permission_overwrites", []):
            if o["id"] == guild_id and int(o.get("allow", 0)) & VIEW_CHANNEL:
                out.append(c)
    return out


def plan_role_permissions(roles: list[dict], *, guild_id: str, creator_role_ids: list[str],
                          staff_role_id: str | None, bot_role_id: str | None,
                          opening: bool) -> list[dict]:
    """Server-level role changes the gate needs; empty = nothing to do (idempotent).

    Gate: @everyone loses View Channels (the only switch unsynced children and future
    channels obey) and creator/staff/bot roles gain it. Open: @everyone gets it back;
    the grants stay — harmless, and removing them could blind role-holders mid-undo.
    All other permission bits are preserved verbatim.
    """
    by_id = {r["id"]: r for r in roles}
    out = []
    if not opening:
        for rid in [*creator_role_ids, staff_role_id, bot_role_id]:
            r = by_id.get(rid)
            if r is None:
                continue
            perms = int(r.get("permissions", 0))
            if not perms & (VIEW_CHANNEL | ADMINISTRATOR):
                out.append({"id": rid, "name": r.get("name", rid), "action": "grant View Channels",
                            "permissions": str(perms | VIEW_CHANNEL)})
    everyone = by_id.get(guild_id)
    if everyone is not None:
        perms = int(everyone.get("permissions", 0))
        if opening and not perms & VIEW_CHANNEL:
            out.append({"id": guild_id, "name": "@everyone", "action": "restore View Channels",
                        "permissions": str(perms | VIEW_CHANNEL)})
        elif not opening and perms & VIEW_CHANNEL:
            # Listed last on purpose: grants land before the lock in the apply loop.
            out.append({"id": guild_id, "name": "@everyone", "action": "remove View Channels",
                        "permissions": str(perms & ~VIEW_CHANNEL)})
    return out


def plan_overwrites(channel: dict, *, guild_id: str, creator_role_ids: list[str],
                    staff_role_id: str | None, onboarding_id: str, opening: bool,
                    bot_role_id: str | None = None) -> list[dict]:
    """The permission overwrites this channel should end up with.

    Existing overwrites for other roles/members are preserved untouched — we only
    own the @everyone / creator-role / staff-role / bot-role entries.
    """
    owned = {guild_id, staff_role_id, bot_role_id, *creator_role_ids} - {None}
    # NOTE: a member-level overwrite for the bot user is NOT in `owned`, so it lands in
    # `kept` and is preserved verbatim — operators who grant the bot directly keep it.
    kept = [o for o in channel.get("permission_overwrites", []) if o["id"] not in owned]

    if channel["id"] == onboarding_id or opening:
        # The onboarding channel (and every channel when --open) stays viewable by all.
        everyone = {"id": guild_id, "type": ROLE, "allow": str(VIEW_CHANNEL), "deny": "0"}
        if channel["id"] == onboarding_id:
            # Preserve the onboarding channel's own send-level rules, which
            # resolve_channels.py set up (view yes, post at channel level no).
            prior = next((o for o in channel.get("permission_overwrites", [])
                          if o["id"] == guild_id), None)
            if prior:
                everyone = {**prior, "allow": str(int(prior.get("allow", 0)) | VIEW_CHANNEL)}
        return kept + [everyone]

    out = [{"id": guild_id, "type": ROLE, "allow": "0", "deny": str(VIEW_CHANNEL)}]
    out += [{"id": rid, "type": ROLE, "allow": str(VIEW_CHANNEL), "deny": "0"}
            for rid in creator_role_ids]
    for rid in (staff_role_id, bot_role_id):
        # The bot's own role is explicitly allowed: without it, gating a category can
        # lock Ace out of the very channels it has to read (campaigns, community-chat).
        if rid:
            out.append({"id": rid, "type": ROLE, "allow": str(VIEW_CHANNEL), "deny": "0"})
    return kept + out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    ap.add_argument("--apply", action="store_true", help="actually write the overwrites")
    ap.add_argument("--open", action="store_true",
                    help="UNDO the gate: make every channel viewable by @everyone again")
    args = ap.parse_args(argv)
    profile = Path(args.profile_dir)

    import yaml

    config = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8")) or {}
    ace = config.get("ace") or {}
    ob = ace.get("onboarding") or {}
    guild_id = str((ace.get("discord") or {}).get("guild_id") or "")
    onboarding_id = str(ob.get("channel_id") or "")
    token = bot_token(profile)

    if not (token and guild_id):
        print("ERROR: missing DISCORD_BOT_TOKEN or guild_id.", file=sys.stderr)
        return 1
    if not onboarding_id and not args.open:
        print("ERROR: no ace.onboarding.channel_id — enable onboarding and run "
              "resolve_channels.py first, so the gate leaves that door open.", file=sys.stderr)
        return 1

    try:
        roles = discord(token, f"/guilds/{guild_id}/roles")
        channels = discord(token, f"/guilds/{guild_id}/channels")
    except urllib.error.HTTPError as exc:
        print(f"ERROR: Discord refused ({exc.code}): {exc.read().decode()[:200]}", file=sys.stderr)
        return 1

    by_name = {r["name"].lower(): r["id"] for r in roles}
    creator_role_ids, missing = [], []
    for want in ob.get("creator_roles") or ["onboarded", "creator"]:
        rid = by_name.get(str(want).lower()) or (str(want) if str(want) in
                                                 {r["id"] for r in roles} else None)
        (creator_role_ids.append(rid) if rid else missing.append(want))
    if missing:
        print(f"ERROR: creator role(s) not found in this server: {missing} — create them "
              "first, or the gate would lock everyone out permanently.", file=sys.stderr)
        return 1
    staff_name = str(ob.get("staff_role") or (ace.get("discord") or {}).get("team_role") or "")
    staff_role_id = by_name.get(staff_name.lower())
    if not staff_role_id:
        print(f"WARNING: staff role {staff_name!r} not found — the team will rely on "
              "Administrator to see gated channels.", file=sys.stderr)

    # The bot's own role/user, so gating can never lock Ace out of the channels it reads.
    try:
        me = discord(token, "/users/@me")
        bot_user_id = me["id"]
        bot_member = discord(token, f"/guilds/{guild_id}/members/{bot_user_id}")
        bot_role_id = next((r for r in bot_member.get("roles", []) if r != guild_id), None)
    except urllib.error.HTTPError:
        bot_user_id = bot_role_id = None

    targets = gate_targets(channels, onboarding_id, guild_id=guild_id,
                           creator_role_ids=creator_role_ids)
    skipped_private = [c.get("name") for c in channels
                       if c.get("type") == 4 and c not in targets
                       and is_already_private(c, guild_id, creator_role_ids)]
    leaks = leaky_channels(channels, guild_id, onboarding_id)
    verb = "OPEN" if args.open else "GATE"

    # Pre-flight: a category that already denies @everyone View, with no explicit allow
    # for the bot's role, is one the bot can no longer manage (Discord resolves Manage
    # Roles through the same overwrite chain). Writing the gate and the bot's allow in
    # the SAME patch avoids this on a fresh server; a server already in that state has
    # to be repaired by hand, so say so loudly instead of emitting bare 403s.
    fenced = []
    for c in targets:
        ows = {o["id"]: o for o in c.get("permission_overwrites", [])}
        everyone_denies = int(ows.get(guild_id, {}).get("deny", 0)) & VIEW_CHANNEL
        # The allow can be granted to the bot's ROLE or directly to the bot USER
        # (a member overwrite) — operators commonly add the bot itself, which is the
        # more precise grant. Either satisfies the check.
        bot_allowed = any(
            ident and int(ows.get(ident, {}).get("allow", 0)) & VIEW_CHANNEL
            for ident in (bot_role_id, bot_user_id)
        )
        if everyone_denies and not bot_allowed:
            fenced.append(c)
    if fenced:
        print("ERROR: the bot cannot manage these — they deny @everyone View Channel and "
              "have no explicit allow for the bot's own role:", file=sys.stderr)
        for c in fenced:
            print(f"  #{c.get('name')}", file=sys.stderr)
        print("Fix in Discord (Edit Channel/Category → Permissions → add the bot's role → "
              "allow View Channel), then re-run. Until then the gate stays as-is and Ace "
              "keeps working; only gate changes are blocked.", file=sys.stderr)
        if args.apply:
            return 1

    # Server-level role gate — grants first, the @everyone lock last (see docstring).
    role_changes = plan_role_permissions(roles, guild_id=guild_id,
                                         creator_role_ids=creator_role_ids,
                                         staff_role_id=staff_role_id,
                                         bot_role_id=bot_role_id, opening=args.open)
    roles_applied, roles_failed = [], []
    bot_perms = next((int(r.get("permissions", 0)) for r in roles if r["id"] == bot_role_id), 0)
    bot_sighted = bool(bot_perms & (VIEW_CHANNEL | ADMINISTRATOR))
    for rc in role_changes:
        line = f"{rc['action']}: {rc['name']}"
        if not args.apply:
            print(f"  would {line}")
            continue
        if rc["id"] == guild_id and not args.open and not bot_sighted:
            print("ERROR: not removing View Channels from @everyone — Ace's own role has "
                  "no View Channels/Administrator and the grant did not land, so the gate "
                  "would blind the bot. Tick View Channels on the bot's role in Discord "
                  "(Server Settings → Roles), then re-run.", file=sys.stderr)
            roles_failed.append(rc["name"])
            continue
        try:
            discord(token, f"/guilds/{guild_id}/roles/{rc['id']}",
                    {"permissions": rc["permissions"]}, method="PATCH")
            print(f"  {line}")
            roles_applied.append(rc["name"])
            if rc["id"] == bot_role_id:
                bot_sighted = True
        except urllib.error.HTTPError as exc:
            print(f"  FAILED {line}: {exc.code} {exc.read().decode()[:120]} — the role "
                  "likely sits at or above the bot's own top role; tick View Channels on "
                  "it in Discord by hand.", file=sys.stderr)
            roles_failed.append(rc["name"])

    home_id = home_channel_id(profile)
    changed = 0
    for channel in sorted(targets, key=lambda c: c.get("position", 0)):
        # The ops/home channel is gated WITHOUT creator allows — staff + bot only.
        chan_creator_ids = [] if channel["id"] == home_id else creator_role_ids
        desired = plan_overwrites(channel, guild_id=guild_id, creator_role_ids=chan_creator_ids,
                                  staff_role_id=staff_role_id, onboarding_id=onboarding_id,
                                  opening=args.open, bot_role_id=bot_role_id)
        current = channel.get("permission_overwrites", [])
        same = {(o["id"], str(o.get("allow", "0")), str(o.get("deny", "0"))) for o in current} == \
               {(o["id"], str(o.get("allow", "0")), str(o.get("deny", "0"))) for o in desired}
        label = "#" + channel.get("name", channel["id"])
        if same:
            continue
        changed += 1
        note = (" (onboarding door — stays visible)" if channel["id"] == onboarding_id
                else " (ops channel — staff+bot only)" if channel["id"] == home_id else "")
        if not args.apply:
            print(f"  would {verb.lower()} {label}{note}")
            continue
        try:
            discord(token, f"/channels/{channel['id']}",
                    {"permission_overwrites": desired}, method="PATCH")
            print(f"  {verb.lower()}d {label}{note}")
        except urllib.error.HTTPError as exc:
            print(f"  FAILED {label}: {exc.code} {exc.read().decode()[:120]}", file=sys.stderr)

    if leaks and not args.open:
        print("\nWARNING: these channels re-allow @everyone to view, which defeats the gate "
              "for them — clear that overwrite in Discord (Edit Channel → Permissions):",
              file=sys.stderr)
        for c in leaks:
            print(f"  #{c.get('name')}", file=sys.stderr)

    print(json.dumps({
        "mode": verb, "applied": bool(args.apply),
        "base_role_gate": ([f"{rc['action']}: {rc['name']}" for rc in role_changes]
                           if not args.apply else
                           {"applied": roles_applied, "failed": roles_failed}),
        "categories_and_orphans_changed": changed,
        "note": "the @everyone base role is the gate; category overwrites are kept for "
                "role-scoped privacy (unsynced children do NOT inherit categories)",
        "creator_roles": creator_role_ids, "staff_role": staff_role_id,
        "bot_role": bot_role_id, "onboarding_channel": onboarding_id,
        "left_private_untouched": skipped_private,
        "leaky_channels": [c.get("name") for c in leaks],
        "next": ("re-run with --apply to write these" if not args.apply else
                 "new members now see only the onboarding channel until Ace assigns their roles"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
