"""Reading back what the agent typed — the view that found the real bugs."""
import json
import sqlite3

import pytest

from _lib import agent_trace


@pytest.fixture
def db(tmp_path):
    """A stand-in for a Hermes profile's state.db, with the columns this tool reads."""
    path = tmp_path / "state.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
        "content TEXT, tool_calls TEXT, tool_name TEXT, timestamp TEXT)")

    def add(session, role, content=None, calls=None, ts="2026-07-23T13:55:35"):
        conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_calls, timestamp) "
            "VALUES (?,?,?,?,?)",
            (session, role, content, json.dumps(calls) if calls else None, ts))

    add("sess_49bbf12d", "user", "[John] [IMPORTANT: skill auto-loaded] …lots of skill… mike-2341")
    add("sess_49bbf12d", "assistant", calls=[{"function": {
        "name": "execute_code",
        "arguments": json.dumps({"code": 'subprocess.run(["python", "onboarding.py", '
                                         '"answer", "--handle", "@john", "--text", ""])'}),
    }}])
    add("sess_49bbf12d", "tool", '{"ok": false, "reason": "blank"}')
    add("sess_49bbf12d", "assistant", "Could you share your TikTok username?")
    add("sess_other", "user", "hello", ts="2026-07-22T09:00:00")
    conn.commit()
    conn.close()
    return path


def test_renders_the_command_the_agent_actually_ran(db):
    conn = agent_trace.connect(db)
    out = agent_trace.render(conn, "sess_49bbf12d")
    assert '"--text", ""' in out          # the dropped message, plainly visible
    assert "CALL execute_code" in out
    assert '"reason": "blank"' in out
    assert "Could you share your TikTok" in out


def test_shows_the_tail_of_the_gateway_payload_where_the_creator_text_lives(db):
    conn = agent_trace.connect(db)
    out = agent_trace.render(conn, "sess_49bbf12d")
    assert "mike-2341" in out             # what they typed, under 7KB of skill


def test_resolves_a_session_from_a_fragment(db):
    conn = agent_trace.connect(db)
    assert agent_trace.resolve_session(conn, "49bbf12d", None) == "sess_49bbf12d"


def test_defaults_to_the_most_recent_session(db):
    conn = agent_trace.connect(db)
    assert agent_trace.resolve_session(conn, None, None) == "sess_49bbf12d"


def test_lists_recent_sessions_newest_first(db):
    conn = agent_trace.connect(db)
    sessions = agent_trace.recent_sessions(conn)
    assert [s["session_id"] for s in sessions] == ["sess_49bbf12d", "sess_other"]


def test_opens_the_database_read_only(db):
    """Never let a debugging tool mutate a live profile's state."""
    conn = agent_trace.connect(db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM messages")


def test_missing_database_is_a_clear_error_not_a_traceback(tmp_path, capsys):
    rc = agent_trace.main(["--profile-dir", str(tmp_path)])
    assert rc == 1
    assert "no Hermes state.db" in capsys.readouterr().err


def test_malformed_tool_calls_do_not_crash_the_render(tmp_path):
    path = tmp_path / "state.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
                 "content TEXT, tool_calls TEXT, tool_name TEXT, timestamp TEXT)")
    conn.execute("INSERT INTO messages (session_id, role, tool_calls, timestamp) "
                 "VALUES ('s','assistant','{not json',  '2026-07-23T00:00:00')")
    conn.commit()
    conn.close()
    assert "session s" in agent_trace.render(agent_trace.connect(path), "s")
