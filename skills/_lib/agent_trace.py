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
    python _lib/agent_trace.py                        # the most recent session
    python _lib/agent_trace.py --session 49bbf12d     # a session id (or any fragment)
    python _lib/agent_trace.py --thread 152984771...  # a Discord thread/channel id
    python _lib/agent_trace.py --list                 # recent sessions to choose from
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

MAX_ARG_CHARS = 800
MAX_RESULT_CHARS = 400


def state_db(profile: Path | None = None) -> Path:
    if profile is None:
        data_dir = os.environ.get("ACE_DATA_DIR")
        profile = Path(data_dir).parent if data_dir else Path(os.environ.get("HERMES_HOME", "."))
    return profile / "state.db"


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def recent_sessions(conn: sqlite3.Connection, limit: int = 15) -> list[dict]:
    rows = conn.execute(
        "SELECT session_id, COUNT(*) AS messages, MAX(timestamp) AS last "
        "FROM messages GROUP BY session_id ORDER BY last DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def resolve_session(conn: sqlite3.Connection, fragment: str | None,
                    thread: str | None) -> str | None:
    if thread:
        row = conn.execute(
            "SELECT session_id FROM messages WHERE session_id LIKE ? "
            "ORDER BY rowid DESC LIMIT 1", (f"%{thread}%",)).fetchone()
        if row:
            return row["session_id"]
    if fragment:
        row = conn.execute(
            "SELECT session_id FROM messages WHERE session_id LIKE ? "
            "ORDER BY rowid DESC LIMIT 1", (f"%{fragment}%",)).fetchone()
        return row["session_id"] if row else None
    sessions = recent_sessions(conn, 1)
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
        stamp = str(row["timestamp"] or "")[11:19]
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
    ap.add_argument("--thread", help="Discord thread/channel id")
    ap.add_argument("--list", action="store_true", help="list recent sessions")
    args = ap.parse_args(argv)

    path = state_db(args.profile_dir)
    if not path.exists():
        print(f"ERROR: no Hermes state.db at {path} — pass --profile-dir.", file=sys.stderr)
        return 1
    conn = connect(path)

    if args.list:
        for s in recent_sessions(conn):
            print(f"{s['last']}  {s['session_id']}  ({s['messages']} messages)")
        return 0

    session_id = resolve_session(conn, args.session, args.thread)
    if not session_id:
        print("ERROR: no matching session. Try --list.", file=sys.stderr)
        return 1
    print(render(conn, session_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
