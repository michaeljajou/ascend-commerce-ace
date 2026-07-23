#!/usr/bin/env python3
"""Show what the AGENT actually did in a Hermes session — the commands, not the timings.

The other half of debugging an Ace failure. ``_lib/trace.py`` records what our scripts saw;
this shows what the agent typed to get there, which is where several bugs actually lived:

  * ``onboarding.py answer --handle @x --text ""`` — the creator's message dropped, so the
    script correctly answered "blank" and Ace re-asked a question they had just answered
  * four consecutive ``uv pip install`` / ``apt-get install`` calls after a script crashed
  * ``python3`` instead of the interpreter that has the bundle's dependencies

Hermes' agent.log records only sizes and durations; the arguments live in the profile's
``state.db``. This reads them out.

Usage:
    python _lib/agent_trace.py                        # the last creator conversation
    python _lib/agent_trace.py --session 49bbf12d     # a session id (or any fragment)
    python _lib/agent_trace.py --user 152957302...    # a creator's Discord user id
    python _lib/agent_trace.py --list                 # recent sessions to choose from
    python _lib/agent_trace.py --list --all           # include cron sessions
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

MAX_ARG_CHARS = 800
MAX_RESULT_CHARS = 400
# Hermes tags cron/agent-initiated runs with this source. Debugging an onboarding means
# looking at a person's conversation, so these are hidden unless asked for — otherwise the
# every-2-minute tick sessions bury the one you want.
BACKGROUND_SOURCE = "cron"


def _clock(value) -> str:
    """HH:MM:SS from Hermes' epoch-float timestamps (ISO strings tolerated too)."""
    try:
        return datetime.fromtimestamp(float(value)).strftime("%H:%M:%S")
    except (TypeError, ValueError):
        text = str(value or "")
        return text[11:19] or "--:--:--"


def state_db(profile: Path | None = None) -> Path:
    if profile is None:
        data_dir = os.environ.get("ACE_DATA_DIR")
        profile = Path(data_dir).parent if data_dir else Path(os.environ.get("HERMES_HOME", "."))
    return profile / "state.db"


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _has_sessions_table(conn: sqlite3.Connection) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone())


def recent_sessions(conn: sqlite3.Connection, limit: int = 15,
                    include_background: bool = False) -> list[dict]:
    """Newest first. The `sessions` table carries who and what; fall back to the message
    log alone if a Hermes build doesn't have it."""
    if _has_sessions_table(conn):
        where = "" if include_background else f"WHERE source IS NOT '{BACKGROUND_SOURCE}'"
        rows = conn.execute(
            f"SELECT id AS session_id, source, user_id, title, started_at, message_count "
            f"FROM sessions {where} ORDER BY started_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]
    rows = conn.execute(
        "SELECT session_id, COUNT(*) AS message_count, MAX(timestamp) AS started_at "
        "FROM messages GROUP BY session_id ORDER BY started_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def resolve_session(conn: sqlite3.Connection, fragment: str | None = None,
                    user: str | None = None,
                    include_background: bool = False) -> str | None:
    """Which session to render. A creator's Discord user id is the useful handle here —
    the Discord thread id never appears in a session id, so matching on it silently
    returned whatever cron job ran most recently."""
    if user and _has_sessions_table(conn):
        row = conn.execute(
            "SELECT id FROM sessions WHERE user_id = ? ORDER BY started_at DESC LIMIT 1",
            (str(user),)).fetchone()
        if row:
            return row["id"]
    if fragment:
        row = conn.execute(
            "SELECT session_id FROM messages WHERE session_id LIKE ? "
            "ORDER BY rowid DESC LIMIT 1", (f"%{fragment}%",)).fetchone()
        return row["session_id"] if row else None
    sessions = recent_sessions(conn, 1, include_background)
    return sessions[0]["session_id"] if sessions else None


def _shorten(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + " …"


def render(conn: sqlite3.Connection, session_id: str) -> str:
    rows = conn.execute(
        "SELECT role, content, tool_calls, tool_name, timestamp FROM messages "
        "WHERE session_id = ? ORDER BY rowid", (session_id,))
    out = [f"session {session_id}", "=" * (8 + len(session_id))]
    for row in rows:
        stamp = _clock(row["timestamp"])
        if row["tool_calls"]:
            try:
                calls = json.loads(row["tool_calls"])
            except (ValueError, TypeError):
                calls = []
            for call in calls:
                fn = call.get("function") or {}
                args = fn.get("arguments")
                try:
                    parsed = json.loads(args)
                    args = parsed.get("code", parsed) if isinstance(parsed, dict) else parsed
                except (ValueError, TypeError):
                    pass
                out.append(f"\n{stamp}  CALL {fn.get('name', '?')}")
                out.append(f"          {_shorten(args, MAX_ARG_CHARS)}")
        elif row["role"] == "tool":
            out.append(f"          -> {_shorten(row['content'] or '', MAX_RESULT_CHARS)}")
        elif row["role"] == "user":
            out.append(f"\n{stamp}  CREATOR (or gateway payload)")
            # The auto-loaded skill is prepended to the creator's own text, so the tail is
            # what they actually typed — the part the agent has to notice.
            body = str(row["content"] or "")
            out.append(f"          …{_shorten(body[-220:], 260)}")
        elif row["role"] == "assistant" and (row["content"] or "").strip():
            out.append(f"\n{stamp}  REPLY: {_shorten(row['content'], 400)}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile-dir", type=Path, default=None)
    ap.add_argument("--session", help="session id or any fragment of one")
    ap.add_argument("--user", help="a creator's Discord user id")
    ap.add_argument("--list", action="store_true", help="list recent sessions")
    ap.add_argument("--all", action="store_true",
                    help="include cron/background sessions (hidden by default)")
    args = ap.parse_args(argv)

    path = state_db(args.profile_dir)
    if not path.exists():
        print(f"ERROR: no Hermes state.db at {path} — pass --profile-dir.", file=sys.stderr)
        return 1
    conn = connect(path)

    if args.list:
        for s in recent_sessions(conn, include_background=args.all):
            bits = [_clock(s.get("started_at")), s["session_id"]]
            if s.get("source"):
                bits.append(f"[{s['source']}]")
            if s.get("user_id"):
                bits.append(f"user={s['user_id']}")
            bits.append(f"({s.get('message_count')} messages)")
            if s.get("title"):
                bits.append(f"— {s['title']}")
            print("  ".join(str(b) for b in bits))
        return 0

    session_id = resolve_session(conn, args.session, args.user, args.all)
    if not session_id:
        print("ERROR: no matching session. Try --list.", file=sys.stderr)
        return 1
    print(render(conn, session_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
