"""Reading back what the agent typed — the view that found the real bugs."""
import json
import sqlite3

import pytest

from _lib import agent_trace


CREATOR_ID = "1529573026839003298"
# Hermes stores timestamps as epoch floats, not ISO strings, and carries session metadata
# in its own table. Getting both wrong in the first draft of this fixture is exactly why
# the tool shipped showing "811148" as a clock and resolving a thread to a cron job.
T0 = 1784814935.5


@pytest.fixture
def db(tmp_path):
    """A stand-in for a Hermes profile's state.db, matching the real schema."""
    path = tmp_path / "state.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
        "content TEXT, tool_calls TEXT, tool_name TEXT, timestamp TEXT)")
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, user_id TEXT, "
        "title TEXT, started_at TEXT, message_count INTEGER)")

    def session(sid, source, user_id, title, started):
        conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?)",
                     (sid, source, user_id, title, str(started), 4))

    def add(sid, role, content=None, calls=None, ts=T0):
        conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_calls, timestamp) "
            "VALUES (?,?,?,?,?)",
            (sid, role, content, json.dumps(calls) if calls else None, str(ts)))

    session("sess_49bbf12d", "discord", CREATOR_ID, "TikTok Onboarding Request", T0)
    add("sess_49bbf12d", "user", "[John] [IMPORTANT: skill auto-loaded] …lots of skill… mike-2341")
    add("sess_49bbf12d", "assistant", calls=[{"function": {
        "name": "execute_code",
        "arguments": json.dumps({"code": 'subprocess.run(["python", "onboarding.py", '
                                         '"answer", "--handle", "@john", "--text", ""])'}),
    }}])
    add("sess_49bbf12d", "tool", '{"ok": false, "reason": "blank"}')
    add("sess_49bbf12d", "assistant", "Could you share your TikTok username?")

    # A cron tick landing AFTER the creator's turn — the every-2-minute jobs are why
    # "most recent session" has to mean "most recent conversation".
    session("cron_af1a69_1000", "cron", None, "nudge-inactive · Jul 23 10:01", T0 + 300)
    add("cron_af1a69_1000", "user", "Run nudge-inactive", ts=T0 + 300)

    session("sess_older", "discord", "999", "Earlier chat", T0 - 5000)
    add("sess_older", "user", "hello", ts=T0 - 5000)
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


def test_timestamps_render_as_a_clock_not_raw_epoch(db):
    conn = agent_trace.connect(db)
    out = agent_trace.render(conn, "sess_49bbf12d")
    assert "811148" not in out                 # what the first version printed
    assert agent_trace._clock(T0) in out
    assert len(agent_trace._clock(T0)) == 8    # HH:MM:SS


def test_resolves_a_session_from_a_fragment(db):
    conn = agent_trace.connect(db)
    assert agent_trace.resolve_session(conn, "49bbf12d") == "sess_49bbf12d"


def test_resolves_the_creators_session_from_their_discord_id(db):
    conn = agent_trace.connect(db)
    assert agent_trace.resolve_session(conn, user=CREATOR_ID) == "sess_49bbf12d"


def test_defaults_to_the_last_conversation_not_the_last_cron_tick(db):
    """The every-2-minute jobs run constantly; "most recent session" must skip them."""
    conn = agent_trace.connect(db)
    assert agent_trace.resolve_session(conn) == "sess_49bbf12d"
    assert agent_trace.resolve_session(conn, include_background=True) == "cron_af1a69_1000"


def test_lists_conversations_newest_first_and_hides_cron_by_default(db):
    conn = agent_trace.connect(db)
    assert [s["session_id"] for s in agent_trace.recent_sessions(conn)] == [
        "sess_49bbf12d", "sess_older"]
    assert "cron_af1a69_1000" in [
        s["session_id"] for s in agent_trace.recent_sessions(conn, include_background=True)]


def test_works_against_a_build_with_no_sessions_table(tmp_path):
    path = tmp_path / "state.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
                 "content TEXT, tool_calls TEXT, tool_name TEXT, timestamp TEXT)")
    conn.execute("INSERT INTO messages (session_id, role, content, timestamp) "
                 "VALUES ('s1','user','hi','1784814935.5')")
    conn.commit()
    conn.close()
    assert agent_trace.resolve_session(agent_trace.connect(path)) == "s1"


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
