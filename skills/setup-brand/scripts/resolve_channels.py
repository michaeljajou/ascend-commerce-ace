#!/usr/bin/env python3
"""Resolve free-response Discord channel NAMES to numeric IDs, post-connect.

Why this is a separate step: Discord channel IDs don't exist in the brand
spec (the operator only knows channel *names* when writing it), and Hermes'
`discord.free_response_channels` gate compares against numeric channel IDs
only. The mapping is only knowable after the brand's gateway has connected
to Discord at least once and built ~/.hermes/channel_directory.json (or the
profile-scoped equivalent).

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
    ace_cfg = config.get("ace") or {}
    scoping = ((ace_cfg.get("discord") or {}).get("scoping")) or {}
    free_response_names = set(scoping.get("free_response", []))

    if not free_response_names:
        print("No free_response channels in ace.discord.scoping — nothing to resolve.")
        return 0

    directory = json.loads(directory_path.read_text(encoding="utf-8"))
    discord_channels = directory.get("platforms", {}).get("discord", [])
    name_to_id = {c["name"]: c["id"] for c in discord_channels if c.get("type") == "channel"}

    resolved_ids = [name_to_id[n] for n in sorted(free_response_names) if n in name_to_id]
    missing = sorted(free_response_names - name_to_id.keys())
    if missing:
        print(f"WARNING: could not resolve channel(s) not yet seen by the bot: {missing}", file=sys.stderr)

    if not resolved_ids:
        print("No channel IDs resolved — is the bot actually in the server yet?", file=sys.stderr)
        return 1

    discord_block = config.setdefault("discord", {})
    discord_block["require_mention"] = discord_block.get("require_mention", True)
    discord_block["free_response_channels"] = ",".join(resolved_ids)

    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(json.dumps({
        "resolved": {n: name_to_id[n] for n in sorted(free_response_names) if n in name_to_id},
        "missing": missing,
        "next": "restart the gateway to pick up discord.free_response_channels",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
