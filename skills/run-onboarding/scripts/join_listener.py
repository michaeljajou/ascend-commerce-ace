#!/usr/bin/env python3
"""Instant onboarding: listen for Discord member-join events, trigger the tick right away.

The cron tick polls every 2 minutes, which means a new creator could wait up to 2 minutes
for their welcome thread. This small always-on process removes that wait: it holds a second
gateway connection (members + guilds intents only, no message content) and the moment
someone joins or leaves, it runs `ace-onboarding-tick.py --joins-only` — so the thread and
welcome message appear within seconds. Zero LLM involvement.

Supervision: the cron tick doubles as this process's watchdog. It spawns the listener when
onboarding is enabled, restarts it if it dies, and stops it when onboarding is disabled.
If the listener is ever down, the 2-minute poll still catches every join — this is a
latency upgrade, never a single point of failure.

NOTE: copied to <profile>/scripts/ace-join-listener.py by setup.py. Runs under the Hermes
venv python (discord.py is available there). Do not run two copies per profile — the
pidfile guards that.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def env_token(profile: Path, key: str) -> str | None:
    if tok := os.environ.get(key):
        return tok
    env_path = profile / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith(f"{key}="):
                return s.split("=", 1)[1].strip().strip("'\"") or None
    return None


def onboarding_enabled(profile: Path) -> bool:
    import yaml

    try:
        config = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8")) or {}
    except OSError:
        return False
    return bool(((config.get("ace") or {}).get("onboarding") or {}).get("enabled"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    args = ap.parse_args(argv)
    profile = Path(args.profile_dir).resolve()

    if not onboarding_enabled(profile):
        print("join-listener: onboarding disabled — not starting.", file=sys.stderr)
        return 0
    token = env_token(profile, "DISCORD_BOT_TOKEN")
    if not token:
        print("join-listener: no DISCORD_BOT_TOKEN — not starting.", file=sys.stderr)
        return 1

    import yaml

    config = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8")) or {}
    guild_id = str(((config.get("ace") or {}).get("discord") or {}).get("guild_id") or "")
    tick_path = profile / "scripts" / "ace-onboarding-tick.py"

    pid_path = profile / "ace" / "onboarding_listener.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")

    import asyncio

    import discord

    intents = discord.Intents.none()
    intents.guilds = True
    intents.members = True  # requires the Server Members privileged intent (portal)
    client = discord.Client(intents=intents)
    run_lock = asyncio.Lock()

    def run_tick() -> None:
        subprocess.run(
            [sys.executable, str(tick_path), "--profile-dir", str(profile), "--joins-only"],
            timeout=120, check=False,
        )

    async def trigger(event: str, member) -> None:
        if guild_id and str(member.guild.id) != guild_id:
            return
        if getattr(member, "bot", False) and event == "join":
            return
        if not onboarding_enabled(profile):  # master switch flipped off → wind down
            await client.close()
            return
        async with run_lock:  # serialize: one tick at a time, bursts queue up
            print(f"join-listener: {event} {member} — running tick.", file=sys.stderr)
            await asyncio.get_running_loop().run_in_executor(None, run_tick)

    @client.event
    async def on_member_join(member):
        await trigger("join", member)

    @client.event
    async def on_member_remove(member):
        await trigger("leave", member)

    @client.event
    async def on_ready():
        print(f"join-listener: connected as {client.user} — instant onboarding active.",
              file=sys.stderr)

    try:
        client.run(token, log_handler=None)
    finally:
        try:
            pid_path.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
