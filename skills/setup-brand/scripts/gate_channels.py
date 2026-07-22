#!/usr/bin/env python3
"""Lock the server until onboarding is done (the Vaulty gate), Discord-natively.

Goal: a brand-new member can see ONLY the onboarding channel. The moment Ace assigns
their `onboarded`/`creator` roles at the end of onboarding, every public channel opens.

How (no holding role needed — this is why it can't race a join):
  - every public channel DENIES View Channel to @everyone
  - each creator role is ALLOWED View Channel on those same channels
  - the onboarding channel keeps its @everyone view (Discord requires parent-channel
    view to see a private thread) — that is the one door left open
  - the staff role is allowed everywhere, so the team never locks itself out

A holding role assigned on join would leave a window where a fast creator sees the
whole server before the bot reacts; permission overwrites apply the instant they land.

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


def plan_overwrites(channel: dict, *, guild_id: str, creator_role_ids: list[str],
                    staff_role_id: str | None, onboarding_id: str, opening: bool) -> list[dict]:
    """The permission overwrites this channel should end up with.

    Existing overwrites for other roles/members are preserved untouched — we only
    own the @everyone / creator-role / staff-role entries.
    """
    owned = {guild_id, staff_role_id, *creator_role_ids} - {None}
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
    if staff_role_id:
        out.append({"id": staff_role_id, "type": ROLE, "allow": str(VIEW_CHANNEL), "deny": "0"})
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

    # Text/voice/forum/announcement channels; categories (type 4) inherit to their children.
    targets = [c for c in channels if c.get("type") in (0, 2, 4, 5, 15)]
    verb = "OPEN" if args.open else "GATE"
    changed = 0
    for channel in sorted(targets, key=lambda c: c.get("position", 0)):
        desired = plan_overwrites(channel, guild_id=guild_id, creator_role_ids=creator_role_ids,
                                  staff_role_id=staff_role_id, onboarding_id=onboarding_id,
                                  opening=args.open)
        current = channel.get("permission_overwrites", [])
        same = {(o["id"], str(o.get("allow", "0")), str(o.get("deny", "0"))) for o in current} == \
               {(o["id"], str(o.get("allow", "0")), str(o.get("deny", "0"))) for o in desired}
        label = "#" + channel.get("name", channel["id"])
        if same:
            continue
        changed += 1
        note = " (onboarding door — stays visible)" if channel["id"] == onboarding_id else ""
        if not args.apply:
            print(f"  would {verb.lower()} {label}{note}")
            continue
        try:
            discord(token, f"/channels/{channel['id']}",
                    {"permission_overwrites": desired}, method="PATCH")
            print(f"  {verb.lower()}d {label}{note}")
        except urllib.error.HTTPError as exc:
            print(f"  FAILED {label}: {exc.code} {exc.read().decode()[:120]}", file=sys.stderr)

    print(json.dumps({
        "mode": verb, "applied": bool(args.apply), "channels_changed": changed,
        "creator_roles": creator_role_ids, "staff_role": staff_role_id,
        "onboarding_channel": onboarding_id,
        "next": ("re-run with --apply to write these" if not args.apply else
                 "new members now see only the onboarding channel until Ace assigns their roles"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
