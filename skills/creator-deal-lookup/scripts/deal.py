#!/usr/bin/env python3
"""Grounding tool: look up a creator's paid-collab / ambassador deal from the profile store.

Used in paid-collab (1:1) and ambassador channels to answer logistics about a specific deal
(terms, rate, schedule, deliverables, payment). Like get-knowledge, a *miss* is the never-fabricate
signal: if no deal is found, escalate — never invent terms.

Prints JSON:
    {"found": true, "handle": "@ava", "terms": {...}}   |   {"found": false, "handle": "@ava"}

Usage:
    python deal.py --handle @ava
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

from _lib import brand, store  # noqa: E402


def run_deal(conn, handle: str) -> dict:
    deal = store.get_deal(conn, handle)
    if deal is None:
        return {"found": False, "handle": handle}
    return {"found": True, "handle": handle, "terms": deal.terms}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Look up a creator's deal terms.")
    ap.add_argument("--handle", required=True)
    args = ap.parse_args(argv)

    profile = brand.profile_dir()
    try:
        if not brand.feature_enabled("general_qa", profile):
            print(json.dumps({"disabled": "general_qa"}))
            return 0
    except brand.PolicyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    conn = store.connect(profile / "ace" / store.DB_FILENAME)
    print(json.dumps(run_deal(conn, args.handle)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
