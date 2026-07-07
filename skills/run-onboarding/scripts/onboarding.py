#!/usr/bin/env python3
"""Creator onboarding state (replaces Vaulty's data collection + role step).

Records the creator, captures TikTok handle + email, tracks retries, completes onboarding,
and gives the team its controls (status / reset / resolve / test-mode / stats). The
conversational guidance lives in the SKILL.md; this script just persists state so the
onboarding tick, `nudge-inactive`, and the digest can use it.

Flow subcommands (used by the agent in the onboarding thread):
    python onboarding.py start    --handle @ava                     # state=collecting
    python onboarding.py set      --handle @ava --tiktok ava.tt     # fields can be set separately
    python onboarding.py set      --handle @ava --email a@x.com
    python onboarding.py retry    --handle @ava                     # returns the running count
    python onboarding.py complete --handle @ava --role Creator      # both fields required
    python onboarding.py guided   --handle @ava                     # guidance done → 48h clock starts

Team subcommands (via admin-commands, or the CLI directly):
    python onboarding.py status   --handle @ava
    python onboarding.py reset    --handle @ava                     # back to the start of the flow
    python onboarding.py resolve  --handle @ava                     # close an escalated case
    python onboarding.py test-mode on|off                           # compressed timers for QA
    python onboarding.py stats
"""

from __future__ import annotations

import argparse
import json
import os
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


def retry(conn, handle: str) -> dict:
    """Count a failed input attempt; the skill flags the team once the limit is hit."""
    row = store.get_onboarding(conn, handle)
    if row is None:
        raise ValueError(f"unknown creator {handle!r}; run start first")
    count = int(row.get("retries") or 0) + 1
    store.update_onboarding(conn, handle, retries=count)
    return {"handle": handle, "retries": count}


def complete(conn, handle: str, role: str = "Creator", now: float | None = None) -> dict:
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


def guided(conn, handle: str, now: float | None = None) -> dict:
    """Guidance sequence delivered — the nudge clock starts here."""
    if store.get_onboarding(conn, handle) is None:
        raise ValueError(f"unknown creator {handle!r}; run start first")
    ts = now if now is not None else time.time()
    store.update_onboarding(conn, handle, onboarding_state="guided", guided_at=str(ts),
                            last_active_at=None)
    return {"handle": handle, "state": "guided"}


def flag(conn, handle: str) -> dict:
    """Stop looping on bad input / blocked step; a human takes over from here."""
    store.update_onboarding(conn, handle, onboarding_state="flagged")
    return {"handle": handle, "state": "flagged"}


def status(conn, handle: str) -> dict:
    row = store.get_onboarding(conn, handle)
    if row is None:
        return {"handle": handle, "state": None, "error": "not found"}
    return {k: row.get(k) for k in (
        "handle", "onboarding_state", "tiktok", "email", "role", "retries",
        "joined_at", "guided_at", "nudged_at", "escalated_at", "resolved_at",
        "last_active_at", "thread_id",
    )}


def reset(conn, handle: str, now: float | None = None) -> dict:
    """Back to the start of the flow (redo / rejoined). Sets state to 'new': the next
    onboarding tick re-onboards them from scratch — fresh private thread (the old one is
    archived; a rejoiner lost access to it anyway when they left) + fresh welcome."""
    if store.get_onboarding(conn, handle) is None:
        raise ValueError(f"unknown creator {handle!r}")
    store.update_onboarding(
        conn, handle, onboarding_state=NEW, tiktok=None, email=None, role=None,
        retries=0, guided_at=None, nudged_at=None, escalated_at=None,
        escalation_channel=None, escalation_ts=None, resolved_at=None, last_active_at=None,
        joined_at=str(now if now is not None else time.time()),
    )
    return {"handle": handle, "state": NEW, "reset": True,
            "next": "the onboarding tick re-onboards them with a fresh thread within ~2 min"}


def resolve(conn, handle: str, now: float | None = None) -> dict:
    """Team closes an escalated case by hand (the ✅ Slack reaction does this automatically)."""
    store.update_onboarding(conn, handle, onboarding_state="resolved",
                            resolved_at=str(now if now is not None else time.time()))
    return {"handle": handle, "state": "resolved"}


def set_test_mode(profile_dir: Path, on: bool) -> dict:
    """Flip ace.onboarding.test_mode in the profile config (compressed timers for QA)."""
    import yaml

    cfg_path = profile_dir / "config.yaml"
    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    ob = config.setdefault("ace", {}).setdefault("onboarding", {})
    ob["test_mode"] = on
    cfg_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return {"test_mode": on, "config": str(cfg_path)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Creator onboarding state + team controls.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "set", "retry", "complete", "guided", "flag", "status", "reset", "resolve"):
        p = sub.add_parser(name)
        p.add_argument("--handle", required=True)
        if name == "set":
            p.add_argument("--tiktok")
            p.add_argument("--email")
        if name == "complete":
            p.add_argument("--role", default="Creator")
    tm = sub.add_parser("test-mode")
    tm.add_argument("state", choices=["on", "off"])
    tm.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    sub.add_parser("stats")
    args = ap.parse_args(argv)

    if args.cmd == "test-mode":
        print(json.dumps(set_test_mode(Path(args.profile_dir), args.state == "on")))
        return 0

    conn = store.connect()
    handlers = {
        "start": lambda: start(conn, args.handle),
        "set": lambda: set_fields(conn, args.handle, args.tiktok, args.email),
        "retry": lambda: retry(conn, args.handle),
        "complete": lambda: complete(conn, args.handle, args.role),
        "guided": lambda: guided(conn, args.handle),
        "flag": lambda: flag(conn, args.handle),
        "status": lambda: status(conn, args.handle),
        "reset": lambda: reset(conn, args.handle),
        "resolve": lambda: resolve(conn, args.handle),
        "stats": lambda: store.onboarding_stats(conn),
    }
    print(json.dumps(handlers[args.cmd]()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
