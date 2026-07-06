#!/usr/bin/env python3
"""Resolve Discord channel NAMES to numeric IDs, post-connect, and wire them in.

Why this is a separate step: Discord channel IDs don't exist in the brand
spec (the operator only knows channel *names* when writing it). The mapping is
only knowable after the brand's gateway has connected to Discord at least once
and built the profile's channel_directory.json.

What it wires (all idempotent):
  1. `discord.free_response_channels` in config.yaml — the channels marked
     free_response in the spec, as numeric IDs (Hermes' gateway gate compares
     IDs only; without this the bot needs an @mention everywhere).
  2. `DISCORD_HOME_CHANNEL` / `DISCORD_HOME_CHANNEL_NAME` in the profile .env —
     Ace's proactive-output channel (cron results, notifications), resolved
     from `ace.discord.home_channel` (default: agent-ace).
  3. The "Channel directory" managed block in SOUL.md — the live
     `#name → <#id>` map so Ace renders clickable channel mentions.
     write_profile preserves this block across setup re-runs.

Run this AFTER the first successful `hermes --profile <brand> gateway run`
connects to Discord (check for "Channel directory built: N target(s)" with
N > 0 in the logs), then restart the gateway once more to pick up the
resolved IDs.

Usage:
    python resolve_channels.py --profile-dir <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # → sibling setup.py
from setup import (  # noqa: E402
    CHANNEL_DIR_END,
    CHANNEL_DIR_START,
    ensure_env,
    upsert_channel_directory,
)

DEFAULT_HOME_CHANNEL = "agent-ace"


def build_directory_block(name_to_id: dict[str, str]) -> str:
    lines = [
        CHANNEL_DIR_START,
        "## Channel directory (auto-generated — do not edit)",
        "When you mention any of these channels, use the clickable tag exactly as shown:",
    ]
    lines += [f"- #{name} → <#{cid}>" for name, cid in sorted(name_to_id.items())]
    lines.append(CHANNEL_DIR_END)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", required=True)
    args = ap.parse_args(argv)

    profile = Path(args.profile_dir)
    config_path = profile / "config.yaml"
    directory_path = profile / "channel_directory.json"

    if not directory_path.exists():
        print(
            f"ERROR: {directory_path} not found. Run the gateway once so it connects "
            "to Discord and builds the channel directory, then re-run this script.",
            file=sys.stderr,
        )
        return 1

    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    ace_discord = ((config.get("ace") or {}).get("discord")) or {}
    scoping = ace_discord.get("scoping") or {}
    free_response_names = set(scoping.get("free_response", []))

    directory = json.loads(directory_path.read_text(encoding="utf-8"))
    discord_channels = directory.get("platforms", {}).get("discord", [])
    name_to_id = {c["name"]: c["id"] for c in discord_channels if c.get("type") == "channel"}
    if not name_to_id:
        print("No channels in the directory — is the bot actually in the server yet?", file=sys.stderr)
        return 1

    # 1. free-response channel IDs → config.yaml (gateway hears these without @mention)
    resolved_ids = [name_to_id[n] for n in sorted(free_response_names) if n in name_to_id]
    missing = sorted(free_response_names - name_to_id.keys())
    if missing:
        print(f"WARNING: could not resolve channel(s) not yet seen by the bot: {missing}", file=sys.stderr)
    if free_response_names:
        discord_block = config.setdefault("discord", {})
        discord_block["require_mention"] = discord_block.get("require_mention", True)
        discord_block["free_response_channels"] = ",".join(resolved_ids)

    # 2. home channel → profile .env (proactive output: cron results, notifications)
    home_name = str(ace_discord.get("home_channel") or DEFAULT_HOME_CHANNEL)
    home_id = name_to_id.get(home_name)
    if home_id:
        ensure_env(profile, {
            "DISCORD_HOME_CHANNEL": home_id,
            "DISCORD_HOME_CHANNEL_NAME": f"#{home_name}",
        })
    else:
        print(
            f"WARNING: home channel #{home_name} not found in the server — create it "
            "(or set discord.home_channel in the brand spec) and re-run.",
            file=sys.stderr,
        )

    # 3. channel-name → <#id> map → SOUL.md managed block (clickable channel mentions)
    soul_path = profile / "SOUL.md"
    soul_updated = False
    if soul_path.exists():
        soul = soul_path.read_text(encoding="utf-8")
        updated = upsert_channel_directory(soul, build_directory_block(name_to_id))
        if updated != soul:
            soul_path.write_text(updated, encoding="utf-8")
        soul_updated = True
    else:
        print(f"WARNING: {soul_path} not found — run setup.py first; skipping channel directory.",
              file=sys.stderr)

    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(json.dumps({
        "resolved": {n: name_to_id[n] for n in sorted(free_response_names) if n in name_to_id},
        "missing": missing,
        "home_channel": {"name": home_name, "id": home_id},
        "soul_channel_directory": soul_updated,
        "next": "restart the gateway to pick up discord.free_response_channels and the home channel",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
