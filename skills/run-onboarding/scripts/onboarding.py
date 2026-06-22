#!/usr/bin/env python3
"""Creator onboarding state (replaces Vaulty's data collection + role step).

Records the creator, captures TikTok handle + email, and completes onboarding. The conversational
guidance (channel overview, how to request samples, current campaigns, intro encouragement) lives
in the SKILL.md; this script just persists state so `nudge-inactive` and the digest can use it.

Usage:
    python onboarding.py start    --handle @ava
    python onboarding.py set      --handle @ava --tiktok ava.tt --email a@x.com
    python onboarding.py complete --handle @ava --role creator
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

from _lib import store  # noqa: E402
from _lib.models import Creator  # noqa: E402

NEW, COLLECTING, COMPLETE = "new", "collecting", "complete"


def start(conn, handle: str, now: float | None = None) -> dict:
    now = now if now is not None else time.time()
    store.upsert_creator(conn, Creator(handle=handle, onboarding_state=COLLECTING, joined_at=str(now)))
    return {"handle": handle, "state": COLLECTING}


def set_fields(conn, handle: str, tiktok: str | None = None, email: str | None = None) -> dict:
    existing = store.get_creator(conn, handle) or Creator(handle=handle, onboarding_state=COLLECTING)
    existing.tiktok = tiktok or existing.tiktok
    existing.email = email or existing.email
    existing.onboarding_state = COLLECTING
    store.upsert_creator(conn, existing)
    return {"handle": handle, "tiktok": existing.tiktok, "email": existing.email}


def complete(conn, handle: str, role: str = "creator", now: float | None = None) -> dict:
    c = store.get_creator(conn, handle)
    if c is None:
        raise ValueError(f"unknown creator {handle!r}; run start first")
    if not (c.tiktok and c.email):
        raise ValueError("cannot complete onboarding without both tiktok and email")
    c.role = role
    c.onboarding_state = COMPLETE
    store.upsert_creator(conn, c)
    store.mark_active(conn, handle, ts=now)
    return {"handle": handle, "state": COMPLETE, "role": role}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Creator onboarding state.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "set", "complete"):
        p = sub.add_parser(name)
        p.add_argument("--handle", required=True)
        if name == "set":
            p.add_argument("--tiktok")
            p.add_argument("--email")
        if name == "complete":
            p.add_argument("--role", default="creator")
    args = ap.parse_args(argv)

    conn = store.connect()
    if args.cmd == "start":
        out = start(conn, args.handle)
    elif args.cmd == "set":
        out = set_fields(conn, args.handle, args.tiktok, args.email)
    else:
        out = complete(conn, args.handle, args.role)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
