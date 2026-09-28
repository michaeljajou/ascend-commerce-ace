#!/usr/bin/env python3
"""Send a Discord DM to a creator (used for the 48h onboarding nudge).

Usage:
    python send_dm.py --user-id <discord_id> --text "..." [--profile-dir <dir>]
    echo "..." | python send_dm.py --user-id <discord_id> --stdin

Exits non-zero when the DM can't be delivered (e.g. the user disallows DMs from the
server) — the calling skill should then fall back to their onboarding thread.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _lib import brand  # noqa: E402

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


def post(token: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{DISCORD_API}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                 "User-Agent": UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def is_guided_creator(profile: Path, user_id: str) -> bool:
    db_path = profile / "ace" / "ace.db"
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = conn.execute(
            """SELECT 1 FROM creators
               WHERE discord_id = ? AND tiktok IS NOT NULL AND role IS NOT NULL
                 AND onboarding_state IN ('guided','nudged') LIMIT 1""",
            (str(user_id),),
        ).fetchone()
        conn.close()
        return row is not None
    except sqlite3.Error:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--text", help="message text (or use --stdin)")
    ap.add_argument("--stdin", action="store_true")
    args = ap.parse_args(argv)

    profile = Path(args.profile_dir)
    try:
        if not brand.feature_enabled("engagement", profile):
            print(json.dumps({"disabled": "engagement"}))
            return 0
    except brand.PolicyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not (brand.config(profile).get("onboarding") or {}).get("enabled"):
        print("ERROR: onboarding is disabled for this profile.", file=sys.stderr)
        return 1
    if not is_guided_creator(profile, args.user_id):
        print("ERROR: engagement DMs require a guided creator record.", file=sys.stderr)
        return 1

    text = (sys.stdin.read() if args.stdin else args.text or "").strip()
    if not text:
        print("ERROR: empty message text.", file=sys.stderr)
        return 1
    token = bot_token(profile)
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not found.", file=sys.stderr)
        return 1

    try:
        dm = post(token, "/users/@me/channels", {"recipient_id": args.user_id})
        sent = post(token, f"/channels/{dm['id']}/messages", {"content": text})
    except urllib.error.HTTPError as exc:
        print(f"ERROR: DM failed (HTTP {exc.code}): {exc.read().decode()[:200]} — the user may "
              "have server DMs disabled; fall back to their onboarding thread.", file=sys.stderr)
        return 1

    print(json.dumps({"sent": sent.get("id"), "dm_channel": dm.get("id")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
