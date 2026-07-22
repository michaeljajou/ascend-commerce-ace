#!/usr/bin/env python3
"""Export the brand's creator records — CSV for the team, or a push to the Sheet.

The SQLite store is always the source of truth. Live rows go to the Google Sheet
automatically when onboarding completes (see _lib/sheet.py); this script covers the
rest: pulling a full CSV, and backfilling/re-syncing the Sheet if it was configured
late or a push failed.

Usage:
    python export_creators.py                 # CSV to stdout
    python export_creators.py --out /tmp/creators.csv
    python export_creators.py --push          # (re)push every completed creator to the Sheet
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

from _lib import sheet, store  # noqa: E402

COLUMNS = ["handle", "tiktok", "email", "phone", "discord_id", "role",
           "onboarding_state", "joined_at", "guided_at", "last_active_at"]
# States that mean "this creator actually finished onboarding with us"
DONE_STATES = ("complete", "guided", "nudged", "active", "escalated", "resolved")


def rows(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM creators WHERE onboarding_state != 'pre_existing' ORDER BY joined_at")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="write CSV here instead of stdout")
    ap.add_argument("--push", action="store_true",
                    help="push completed creators to the configured Google Sheet")
    args = ap.parse_args(argv)

    conn = store.connect()
    data = rows(conn)

    if args.push:
        ace = sheet.brand_config()
        if not sheet.webhook_url(ace):
            print("ERROR: no ace.onboarding.sheet_webhook configured for this brand — "
                  "add the Apps Script URL to config.yaml first (see _lib/sheet.py).",
                  file=sys.stderr)
            return 1
        pushed = sum(1 for r in data if r["onboarding_state"] in DONE_STATES
                     and sheet.sync_creator(r, status=r["onboarding_state"]))
        print(f"pushed {pushed} creator(s) to the sheet")
        return 0

    handle = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
    try:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    finally:
        if args.out:
            handle.close()
            print(f"wrote {len(data)} creator(s) to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
