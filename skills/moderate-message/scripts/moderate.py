#!/usr/bin/env python3
"""Resolve + record a moderation decision for one message.

Given the detected category (from `detect-sentiment`) and the creator's recent history, this
returns the tier + action the skill should carry out, and records the event so repeat behavior
escalates. Decision logic lives in `_lib/moderation` (pure, tested); this wires it to the store.

Usage:
    python moderate.py --handle @ava --category negative_sentiment --channel community-chat
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

from _lib import moderation, store  # noqa: E402

HOUR = 3600.0


def run_moderate(
    conn,
    handle: str,
    category: str,
    channel: str | None = None,
    lookback_h: float = 24,
    now: float | None = None,
) -> dict:
    now = now if now is not None else time.time()
    prior = store.recent_moderation_count(conn, handle, since_ts=now - lookback_h * HOUR)
    decision = moderation.resolve(category, prior, channel)
    store.record_moderation(
        conn,
        tier=decision.tier,
        action=decision.action,
        creator_handle=handle,
        channel=channel,
        reason=category,
        ts=now,
    )
    return {
        "tier": decision.tier,
        "action": decision.action,
        "notify_team": decision.notify_team,
        "redirect_thread": decision.redirect_thread,
        "prior_count": prior,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Resolve + record a moderation decision.")
    ap.add_argument("--handle", required=True)
    ap.add_argument("--category", required=True, choices=sorted(moderation.CATEGORIES))
    ap.add_argument("--channel")
    ap.add_argument("--lookback-h", type=float, default=24)
    args = ap.parse_args(argv)

    conn = store.connect()
    print(json.dumps(run_moderate(conn, args.handle, args.category, args.channel, args.lookback_h)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
