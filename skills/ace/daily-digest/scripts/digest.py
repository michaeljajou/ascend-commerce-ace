#!/usr/bin/env python3
"""Build the 9 AM daily digest for the brand's Slack channel.

Aggregates the last 24h from the profile store into a skimmable summary: interactions
(answered vs escalated/routed), sentiment/moderation flags, new members + onboarding status,
and upcoming deal deadlines. Pure `build_digest` so it's unit-testable.

Usage:
    python digest.py [--hours 24] [--deadline-days 7]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills/ace

from _lib import store  # noqa: E402

HOUR = 3600.0


def _new_members(conn, since_ts: float) -> list[dict]:
    rows = conn.execute(
        "SELECT handle, onboarding_state FROM creators WHERE joined_at IS NOT NULL AND CAST(joined_at AS REAL) >= ?",
        (since_ts,),
    ).fetchall()
    return [{"handle": r["handle"], "onboarding_state": r["onboarding_state"]} for r in rows]


def _upcoming_deadlines(conn, now: float, within_days: int) -> list[dict]:
    """Deals whose terms.due (ISO date) falls within the next `within_days`."""
    import json as _json

    today = datetime.fromtimestamp(now).date()
    out: list[dict] = []
    for r in conn.execute("SELECT creator_handle, terms_json FROM deals").fetchall():
        terms = _json.loads(r["terms_json"])
        due = terms.get("due")
        if not due:
            continue
        try:
            due_date = date.fromisoformat(str(due))
        except ValueError:
            continue
        delta = (due_date - today).days
        if 0 <= delta <= within_days:
            out.append({"handle": r["creator_handle"], "due": due, "in_days": delta})
    return sorted(out, key=lambda d: d["in_days"])


def build_digest(conn, now: float | None = None, hours: float = 24, deadline_days: int = 7) -> dict:
    now = now if now is not None else time.time()
    since = now - hours * HOUR
    m = store.metrics_since(conn, since)
    return {
        "window_hours": hours,
        "interactions": m,
        "new_members": _new_members(conn, since),
        "upcoming_deadlines": _upcoming_deadlines(conn, now, deadline_days),
    }


def render_digest(d: dict) -> str:
    m = d["interactions"]
    lines = [
        f"*Ace daily digest* (last {int(d['window_hours'])}h)",
        f"• Interactions: {m['total']}  (answered {m['answered']} / escalated {m['escalated']} / routed {m['routed']})",
        f"• Answer rate: {int(m['answer_rate'] * 100)}%   👍 {m['thumbs_up']} / 👎 {m['thumbs_down']}",
        f"• Moderation actions: {m['moderation_actions']}",
        f"• New members: {len(d['new_members'])}"
        + (f" ({sum(1 for x in d['new_members'] if x['onboarding_state'] != 'complete')} mid-onboarding)"
           if d["new_members"] else ""),
    ]
    if d["upcoming_deadlines"]:
        nearest = ", ".join(f"{x['handle']} ({x['in_days']}d)" for x in d["upcoming_deadlines"][:5])
        lines.append(f"• Upcoming deadlines: {nearest}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the daily digest.")
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--deadline-days", type=int, default=7)
    args = ap.parse_args(argv)

    conn = store.connect()
    d = build_digest(conn, hours=args.hours, deadline_days=args.deadline_days)
    print(json.dumps({"digest": d, "text": render_digest(d)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
