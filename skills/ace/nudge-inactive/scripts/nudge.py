#!/usr/bin/env python3
"""Find creators to nudge (48h inactive) or flag to the team (7d inactive).

Cron-driven (blueprint). Buckets onboarded creators by how long they've been inactive:
  - inactive between `nudge_after_h` and `flag_after_h`  → gentle nudge (DM/mention)
  - inactive longer than `flag_after_h`                  → flag to the team in Slack

Usage:
    python nudge.py [--nudge-after-h 48] [--flag-after-h 168]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills/ace

from _lib import store  # noqa: E402

HOUR = 3600.0


def run_nudges(
    conn,
    now: float | None = None,
    nudge_after_h: float = 48,
    flag_after_h: float = 168,  # 7 days
) -> dict:
    now = now if now is not None else time.time()
    flag = store.list_inactive_creators(conn, since_ts=now - flag_after_h * HOUR)
    nudge_window = store.list_inactive_creators(conn, since_ts=now - nudge_after_h * HOUR)
    flag_handles = {c.handle for c in flag}
    nudge_handles = [c.handle for c in nudge_window if c.handle not in flag_handles]
    return {"nudge": sorted(nudge_handles), "flag": sorted(flag_handles)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Select inactive creators to nudge/flag.")
    ap.add_argument("--nudge-after-h", type=float, default=48)
    ap.add_argument("--flag-after-h", type=float, default=168)
    args = ap.parse_args(argv)

    conn = store.connect()
    print(json.dumps(run_nudges(conn, nudge_after_h=args.nudge_after_h, flag_after_h=args.flag_after_h)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
