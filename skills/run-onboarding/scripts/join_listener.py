#!/usr/bin/env python3
"""Instant onboarding, fleet edition: ONE listener process for every brand.

The cron tick polls every 2 minutes, so without this a new creator could wait up to
2 minutes for their welcome thread. This process removes the wait: it holds a Discord
gateway connection per bot token (members + guilds intents only, no message content),
and the moment someone joins or leaves any brand's server it runs that brand's
`ace-onboarding-tick.py --joins-only`. The thread appears in seconds. Zero LLM.

Why one process for all brands: each Python process costs ~40MB before doing anything,
so per-brand listeners would burn ~55MB x N. This one costs the base once plus a small
slice per connection, which matters on a fixed-size VPS.

How it self-manages:
  - On start (and every RESCAN_SECONDS) it scans <root>/profiles/*/config.yaml and
    listens for every brand with ace.onboarding.enabled: true.
  - Brands enabled later are picked up on the next rescan; disabled brands are dropped.
  - When zero brands are enabled it exits (the ticks only respawn it while needed).

Supervision: every enabled brand's cron tick acts as watchdog — if this process dies,
the next tick (any brand) respawns it, and the 2-minute poll still catches every join
meanwhile. Latency upgrade, never a single point of failure. The pidfile at
<root>/ace-join-listener.pid keeps it a singleton.

NOTE: copied to <profile>/scripts/ace-join-listener.py by setup.py; runs under the
Hermes venv python (discord.py available there). Launched with --profile-dir of
whichever brand spawned it; the fleet root is derived from that path.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

RESCAN_SECONDS = 60


def derive_root(profile: Path) -> Path:
    """Fleet root from any profile path: <root>/profiles/<brand> → <root>.
    Degenerate case (no profiles/ parent — tests, single-home setups): the profile
    itself is the root and the only candidate brand."""
    p = profile.resolve()
    return p.parents[1] if p.parent.name == "profiles" else p


def env_token(profile: Path, key: str = "DISCORD_BOT_TOKEN") -> str | None:
    env_path = profile / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith(f"{key}="):
                return s.split("=", 1)[1].strip().strip("'\"") or None
    return None


def discover(root: Path) -> list[dict]:
    """Every brand under the fleet root with onboarding enabled → its wiring."""
    import yaml

    profiles_dir = root / "profiles"
    candidates = sorted(p for p in profiles_dir.iterdir() if p.is_dir()) \
        if profiles_dir.is_dir() else [root]
    out = []
    for profile in candidates:
        cfg_path = profile / "config.yaml"
        if not cfg_path.exists():
            continue
        try:
            config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        ace = config.get("ace") or {}
        if not (ace.get("onboarding") or {}).get("enabled"):
            continue
        guild_id = str((ace.get("discord") or {}).get("guild_id") or "")
        token = env_token(profile)
        if guild_id and token and (profile / "scripts" / "ace-onboarding-tick.py").exists():
            out.append({"profile": str(profile), "guild_id": guild_id, "token": token})
    return out


def group_by_token(entries: list[dict]) -> dict[str, dict[str, str]]:
    """token → {guild_id → profile_path}. Brands sharing one bot share one connection."""
    grouped: dict[str, dict[str, str]] = {}
    for e in entries:
        grouped.setdefault(e["token"], {})[e["guild_id"]] = e["profile"]
    return grouped


def pid_alive(pid_path: Path) -> int | None:
    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    args = ap.parse_args(argv)
    root = derive_root(Path(args.profile_dir))

    pid_path = root / "ace-join-listener.pid"
    if pid_alive(pid_path):
        print("join-listener: another instance is already running — exiting.", file=sys.stderr)
        return 0
    entries = discover(root)
    if not entries:
        print("join-listener: no brands with onboarding enabled — exiting.", file=sys.stderr)
        return 0
    pid_path.write_text(str(os.getpid()), encoding="utf-8")

    import asyncio

    import discord

    def run_tick(profile: str) -> None:
        subprocess.run(
            [sys.executable, str(Path(profile) / "scripts" / "ace-onboarding-tick.py"),
             "--profile-dir", profile, "--joins-only"],
            timeout=120, check=False,
        )

    async def fleet() -> None:
        routes: dict[str, str] = {}            # guild_id → profile (live, shared)
        clients: dict[str, discord.Client] = {}  # token → client
        tick_locks: dict[str, asyncio.Lock] = {}
        loop = asyncio.get_running_loop()

        async def handle(event: str, member) -> None:
            profile = routes.get(str(member.guild.id))
            if not profile or (event == "join" and getattr(member, "bot", False)):
                return
            lock = tick_locks.setdefault(profile, asyncio.Lock())
            async with lock:  # serialize per brand; bursts queue up
                print(f"join-listener: {event} {member} → tick for {Path(profile).name}",
                      file=sys.stderr)
                await loop.run_in_executor(None, run_tick, profile)

        def make_client() -> discord.Client:
            intents = discord.Intents.none()
            intents.guilds = True
            intents.members = True  # needs the Server Members privileged intent (portal)
            client = discord.Client(intents=intents)

            @client.event
            async def on_member_join(member):
                await handle("join", member)

            @client.event
            async def on_member_remove(member):
                await handle("leave", member)

            @client.event
            async def on_ready():
                print(f"join-listener: connected as {client.user} "
                      f"({len(client.guilds)} server(s)) — instant onboarding active.",
                      file=sys.stderr)

            return client

        def sync_fleet() -> bool:
            """Reconcile clients/routes with what's enabled on disk. False = nothing left."""
            grouped = group_by_token(discover(root))
            routes.clear()
            for guild_map in grouped.values():
                routes.update(guild_map)
            for token in grouped:
                if token not in clients:
                    clients[token] = make_client()
                    asyncio.ensure_future(clients[token].start(token))
                    print("join-listener: starting a connection for a newly enabled brand.",
                          file=sys.stderr)
            for token in list(clients):
                if token not in grouped:
                    asyncio.ensure_future(clients.pop(token).close())
                    print("join-listener: dropped a connection (brand disabled).", file=sys.stderr)
            return bool(grouped)

        sync_fleet()
        while True:
            await asyncio.sleep(RESCAN_SECONDS)
            if not sync_fleet():
                print("join-listener: no enabled brands remain — shutting down.", file=sys.stderr)
                for client in clients.values():
                    await client.close()
                return

    try:
        asyncio.run(fleet())
    finally:
        try:
            pid_path.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
