#!/usr/bin/env python3
"""Find onboarded creators to nudge (48h inactive).

Cron-driven (blueprint). Selects completed creators inactive for more than `nudge_after_h`
and at most `max_inactive_h`. Anyone quieter than that is left alone: the 7-day "still
inactive" Slack flag was removed on 2026-10-06 — #ace-escalations holds only posts that
need the team to act, and a creator who drifted off is not one of them.

Usage:
    python nudge.py [--nudge-after-h 48] [--max-inactive-h 168]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

from _lib import brand, store  # noqa: E402

HOUR = 3600.0


def run_nudges(
    conn,
    now: float | None = None,
    nudge_after_h: float = 48,
    max_inactive_h: float = 168,  # 7 days — quieter than this is left alone
) -> dict:
    now = now if now is not None else time.time()
    too_quiet = {c.handle for c in
                 store.list_inactive_creators(conn, since_ts=now - max_inactive_h * HOUR)}
    nudge_window = store.list_inactive_creators(conn, since_ts=now - nudge_after_h * HOUR)
    return {"nudge": sorted(c.handle for c in nudge_window if c.handle not in too_quiet)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Select inactive creators to nudge.")
    ap.add_argument("--nudge-after-h", type=float, default=48)
    ap.add_argument("--max-inactive-h", type=float, default=168,
                    help="creators quieter than this are left alone (default 7 days)")
    args = ap.parse_args(argv)

    try:
        if not brand.feature_enabled("engagement"):
            print(json.dumps({"disabled": "engagement"}))
            return 0
    except brand.PolicyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    conn = store.connect()
    print(json.dumps(run_nudges(conn, nudge_after_h=args.nudge_after_h,
                                max_inactive_h=args.max_inactive_h)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
