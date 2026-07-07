"""onboarding_tick.py: zero-token joins/leavers/engagement/timers — agent only for nudges."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import onboarding_tick as tick  # noqa: E402

# Real now: the pure-function tests pass this in explicitly, and the main() integration
# tests build row timestamps relative to it (main uses actual wall-clock time).
NOW = datetime.now(timezone.utc)


def ts_ago(**kw) -> str:
    return str((NOW - timedelta(**kw)).timestamp())


# ── pure decision helpers ──────────────────────────────────────────────────────

def test_effective_windows_and_test_mode():
    assert tick.effective_windows({}) == (timedelta(hours=48), timedelta(days=7))
    assert tick.effective_windows({"nudge_hours": 24, "escalate_days": 3}) == (
        timedelta(hours=24), timedelta(days=3))
    assert tick.effective_windows({"test_mode": True}) == (
        timedelta(minutes=3), timedelta(minutes=8))


def test_is_new_joiner_filters_bots_known_and_team():
    known = {"10"}
    assert tick.is_new_joiner({"user": {"id": "11", "username": "new"}, "roles": []}, known, "r1")
    assert not tick.is_new_joiner({"user": {"id": "10", "username": "old"}, "roles": []}, known, "r1")
    assert not tick.is_new_joiner({"user": {"id": "12", "bot": True}, "roles": []}, known, "r1")
    assert not tick.is_new_joiner({"user": {"id": "13", "username": "staff"}, "roles": ["r1"]}, known, "r1")


def test_due_nudges_only_quiet_guided_creators():
    rows = [
        {"handle": "@due", "onboarding_state": "guided", "guided_at": ts_ago(hours=49), "nudged_at": None},
        {"handle": "@fresh", "onboarding_state": "guided", "guided_at": ts_ago(hours=2), "nudged_at": None},
        {"handle": "@already", "onboarding_state": "guided", "guided_at": ts_ago(hours=90), "nudged_at": ts_ago(hours=1)},
        {"handle": "@active", "onboarding_state": "active", "guided_at": ts_ago(hours=90), "nudged_at": None},
    ]
    assert [r["handle"] for r in tick.due_nudges(rows, NOW, timedelta(hours=48))] == ["@due"]


def test_due_escalations_only_after_window_since_join():
    rows = [
        {"handle": "@due", "onboarding_state": "nudged", "joined_at": ts_ago(days=8)},
        {"handle": "@guided-due", "onboarding_state": "guided", "joined_at": ts_ago(days=7, hours=1)},
        {"handle": "@fresh", "onboarding_state": "nudged", "joined_at": ts_ago(days=3)},
        {"handle": "@escalated", "onboarding_state": "escalated", "joined_at": ts_ago(days=9)},
    ]
    got = [r["handle"] for r in tick.due_escalations(rows, NOW, timedelta(days=7))]
    assert got == ["@due", "@guided-due"]


def test_escalation_text_has_all_required_fields():
    text = tick.escalation_text({
        "handle": "@quiet", "joined_at": ts_ago(days=7), "discord_id": "42",
        "tiktok": "q.tt", "email": None, "guided_at": ts_ago(days=6), "nudged_at": ts_ago(days=4),
    }, "Glow Labs", NOW)
    assert "[Glow Labs]" in text and "@quiet" in text
    assert "7d ago" in text and "gave TikTok (q.tt)" in text and "was nudged" in text
    assert "discord.com/users/42" in text and "✅" in text


# ── main(): integration with mocked REST ───────────────────────────────────────

def make_profile(tmp_path, *, enabled=True, test_mode=True, channel_id="900"):
    ob = {"enabled": enabled, "test_mode": test_mode, "channel_id": channel_id,
          "creator_roles": ["Creator"], "slack_channel": "#ace-escalations"}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"ace": {
        "brand_id": "pilot", "brand_name": "Pilot",
        "discord": {"guild_id": "g1", "team_role": "Ascend Team"},
        "onboarding": ob,
    }}), encoding="utf-8")
    (tmp_path / "channel_directory.json").write_text(json.dumps({"platforms": {"discord": [
        {"id": "555", "name": "community-chat", "type": "channel"},
        {"id": "900", "name": "onboarding", "type": "channel"},
    ]}}), encoding="utf-8")
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=dtok\nSLACK_BOT_TOKEN=stok\n", encoding="utf-8")
    return tmp_path


class FakeAPIs:
    """Programmable fakes for the discord()/slack() helpers, recording writes."""

    def __init__(self, members=(), messages=None):
        self.members = list(members)
        self.messages = messages or {}     # channel_id → list
        self.writes = []                   # (path, payload, method)
        self.slack_calls = []
        self.reactions = {}                # ts → [names]
        self.thread_seq = 7000

    def discord(self, token, path, payload=None, method=None):
        if payload is not None or method:
            self.writes.append((path, payload, method))
            if path.endswith("/threads"):
                self.thread_seq += 1
                return {"id": str(self.thread_seq)}
            return {}
        if "/guilds/g1/members?" in path:
            return self.members if "after=0" in path else []
        if path == "/guilds/g1/roles":
            return [{"id": "r1", "name": "Ascend Team"}, {"id": "r2", "name": "Creator"}]
        if "/messages?limit=1" in path:
            cid = path.split("/channels/")[1].split("/")[0]
            return self.messages.get(cid, [])[:1]
        if "/messages?after=" in path:
            cid = path.split("/channels/")[1].split("/")[0]
            after = int(path.split("after=")[1].split("&")[0])
            return [m for m in self.messages.get(cid, []) if int(m["id"]) > after]
        raise AssertionError(f"unexpected discord call: {path}")

    def slack(self, token, method, payload):
        self.slack_calls.append((method, payload))
        if method == "chat.postMessage":
            return {"ok": True, "channel": "C1", "ts": "111.222"}
        if method == "reactions.get":
            names = self.reactions.get(payload["timestamp"], [])
            return {"ok": True, "message": {"reactions": [{"name": n} for n in names]}}
        raise AssertionError(method)


def run_tick(tmp_path, monkeypatch, fakes):
    monkeypatch.setattr(tick, "discord", fakes.discord)
    monkeypatch.setattr(tick, "slack", fakes.slack)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = tick.main(["--profile-dir", str(tmp_path)])
    assert rc == 0
    return buf.getvalue().strip()


def seed_state(tmp_path, **extra):
    (tmp_path / "ace").mkdir(exist_ok=True)
    state = {"member_baseline_done": True, "team_role_id": "r1",
             "cursors": {"555": "100"}, **extra}
    (tmp_path / "ace" / "onboarding_tick_state.json").write_text(json.dumps(state))


def db_row(tmp_path, handle):
    conn = tick.open_db(tmp_path)
    r = conn.execute("SELECT * FROM creators WHERE handle=?", (handle,)).fetchone()
    return dict(r) if r else None


def test_disabled_is_inert(tmp_path, monkeypatch):
    make_profile(tmp_path, enabled=False)
    out = run_tick(tmp_path, monkeypatch, FakeAPIs())
    assert json.loads(out) == {"wakeAgent": False}


def test_first_tick_baselines_without_onboarding(tmp_path, monkeypatch):
    make_profile(tmp_path)
    fakes = FakeAPIs(members=[
        {"user": {"id": "1", "username": "veteran"}, "roles": []},
        {"user": {"id": "2", "username": "staffer"}, "roles": ["r1"]},
    ])
    out = run_tick(tmp_path, monkeypatch, fakes)
    assert json.loads(out) == {"wakeAgent": False}
    assert db_row(tmp_path, "@veteran")["onboarding_state"] == "pre_existing"
    assert not any(p.endswith("/threads") for p, _, _ in fakes.writes)   # no threads created


def test_new_joiner_gets_thread_welcome_and_record(tmp_path, monkeypatch):
    make_profile(tmp_path)
    seed_state(tmp_path)
    fakes = FakeAPIs(members=[{"user": {"id": "77", "username": "newbie"}, "roles": []}])
    out = run_tick(tmp_path, monkeypatch, fakes)
    assert json.loads(out) == {"wakeAgent": False}
    row = db_row(tmp_path, "@newbie")
    assert row["onboarding_state"] == "collecting" and row["discord_id"] == "77"
    assert row["thread_id"] == "7001"
    paths = [p for p, _, _ in fakes.writes]
    assert "/channels/900/threads" in paths                              # private thread
    assert "/channels/7001/thread-members/77" in paths                   # creator added
    welcome = next(pl for p, pl, _ in fakes.writes if p == "/channels/7001/messages")
    assert "TikTok username" in welcome["content"] and "<@77>" in welcome["content"]


def test_duplicate_join_does_not_restart(tmp_path, monkeypatch):
    make_profile(tmp_path)
    seed_state(tmp_path)
    conn = tick.open_db(tmp_path)
    conn.execute("INSERT INTO creators (handle, onboarding_state, discord_id, thread_id, guided_at, joined_at)"
                 " VALUES ('@newbie','guided','77','7001',?,?)", (ts_ago(minutes=1), ts_ago(minutes=2)))
    conn.commit()
    fakes = FakeAPIs(members=[{"user": {"id": "77", "username": "newbie"}, "roles": []}])
    run_tick(tmp_path, monkeypatch, fakes)
    assert db_row(tmp_path, "@newbie")["onboarding_state"] == "guided"   # resumed, not restarted
    assert not any(p.endswith("/threads") for p, _, _ in fakes.writes)


def test_leaver_mid_flow_stops_timers_and_archives(tmp_path, monkeypatch):
    make_profile(tmp_path)
    seed_state(tmp_path)
    conn = tick.open_db(tmp_path)
    conn.execute("INSERT INTO creators (handle, onboarding_state, discord_id, thread_id, joined_at)"
                 " VALUES ('@gone','collecting','88','7005',?)", (ts_ago(minutes=30),))
    conn.commit()
    fakes = FakeAPIs(members=[])                                         # they left
    run_tick(tmp_path, monkeypatch, fakes)
    assert db_row(tmp_path, "@gone")["onboarding_state"] == "left"
    assert ("/channels/7005", {"archived": True, "locked": False}, "PATCH") in fakes.writes


def test_engagement_stops_the_clock(tmp_path, monkeypatch):
    make_profile(tmp_path)
    seed_state(tmp_path)
    conn = tick.open_db(tmp_path)
    conn.execute("INSERT INTO creators (handle, onboarding_state, discord_id, thread_id, guided_at, joined_at)"
                 " VALUES ('@chatty','guided','77','7001',?,?)", (ts_ago(minutes=30), ts_ago(minutes=40)))
    conn.commit()
    fakes = FakeAPIs(
        members=[{"user": {"id": "77", "username": "chatty"}, "roles": []}],
        messages={"555": [{"id": "101", "author": {"id": "77"}}]},       # posted in community-chat
    )
    out = run_tick(tmp_path, monkeypatch, fakes)
    assert db_row(tmp_path, "@chatty")["onboarding_state"] == "active"
    assert json.loads(out) == {"wakeAgent": False}                       # no nudge for active creators


def test_quiet_creator_gets_nudge_wake_once(tmp_path, monkeypatch):
    make_profile(tmp_path)                                               # test_mode: nudge at 3 min
    seed_state(tmp_path)
    conn = tick.open_db(tmp_path)
    conn.execute("INSERT INTO creators (handle, onboarding_state, discord_id, thread_id, guided_at, joined_at)"
                 " VALUES ('@quiet','guided','77','7001',?,?)", (ts_ago(minutes=5), ts_ago(minutes=6)))
    conn.commit()
    fakes = FakeAPIs(members=[{"user": {"id": "77", "username": "quiet"}, "roles": []}])
    out = run_tick(tmp_path, monkeypatch, fakes)
    payload = json.loads(out)
    assert payload["onboarding_nudges_due"][0]["handle"] == "@quiet"     # agent woken
    assert db_row(tmp_path, "@quiet")["onboarding_state"] == "nudged"    # marked on emit
    out2 = run_tick(tmp_path, monkeypatch, fakes)
    assert json.loads(out2) == {"wakeAgent": False}                      # never nudged twice


def test_escalation_posts_to_slack_and_resolves_on_checkmark(tmp_path, monkeypatch):
    make_profile(tmp_path)                                               # test_mode: escalate at 8 min
    seed_state(tmp_path)
    conn = tick.open_db(tmp_path)
    conn.execute("INSERT INTO creators (handle, onboarding_state, discord_id, thread_id, nudged_at, guided_at, joined_at)"
                 " VALUES ('@silent','nudged','77','7001',?,?,?)",
                 (ts_ago(minutes=5), ts_ago(minutes=8), ts_ago(minutes=9)))
    conn.commit()
    fakes = FakeAPIs(members=[{"user": {"id": "77", "username": "silent"}, "roles": []}])
    run_tick(tmp_path, monkeypatch, fakes)
    row = db_row(tmp_path, "@silent")
    assert row["onboarding_state"] == "escalated" and row["escalation_ts"] == "111.222"
    method, payload = fakes.slack_calls[0]
    assert method == "chat.postMessage" and "[Pilot]" in payload["text"]

    fakes.reactions["111.222"] = ["white_check_mark"]                    # team clicks ✅
    run_tick(tmp_path, monkeypatch, fakes)
    assert db_row(tmp_path, "@silent")["onboarding_state"] == "resolved"


def test_unreadable_channel_does_not_abort_the_tick(tmp_path, monkeypatch):
    """A private channel the bot can't read (403) must not kill the whole pass."""
    import urllib.error

    make_profile(tmp_path)
    seed_state(tmp_path)
    (tmp_path / "channel_directory.json").write_text(json.dumps({"platforms": {"discord": [
        {"id": "666", "name": "private-team", "type": "channel"},   # bot can't read this
        {"id": "555", "name": "community-chat", "type": "channel"},
        {"id": "900", "name": "onboarding", "type": "channel"},
    ]}}), encoding="utf-8")
    fakes = FakeAPIs(members=[{"user": {"id": "77", "username": "newbie"}, "roles": []}])
    real_discord = fakes.discord

    def discord_with_403(token, path, payload=None, method=None):
        if "/channels/666/" in path:
            raise urllib.error.HTTPError(path, 403, "Forbidden", None, None)
        return real_discord(token, path, payload, method)

    monkeypatch.setattr(tick, "discord", discord_with_403)
    monkeypatch.setattr(tick, "slack", fakes.slack)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert tick.main(["--profile-dir", str(tmp_path)]) == 0
    assert db_row(tmp_path, "@newbie")["onboarding_state"] == "collecting"   # join still processed


def test_joins_only_onboards_but_never_touches_timers(tmp_path, monkeypatch):
    """Listener-triggered runs handle joins; nudges must stay with the cron run
    (only cron output can wake the agent)."""
    make_profile(tmp_path)
    seed_state(tmp_path)
    conn = tick.open_db(tmp_path)
    conn.execute("INSERT INTO creators (handle, onboarding_state, discord_id, thread_id, guided_at, joined_at)"
                 " VALUES ('@quiet','guided','66','7009',?,?)", (ts_ago(minutes=5), ts_ago(minutes=6)))
    conn.commit()
    fakes = FakeAPIs(members=[
        {"user": {"id": "66", "username": "quiet"}, "roles": []},
        {"user": {"id": "77", "username": "newbie"}, "roles": []},
    ])
    monkeypatch.setattr(tick, "discord", fakes.discord)
    monkeypatch.setattr(tick, "slack", fakes.slack)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert tick.main(["--profile-dir", str(tmp_path), "--joins-only"]) == 0
    assert json.loads(buf.getvalue().strip()) == {"wakeAgent": False}
    assert db_row(tmp_path, "@newbie")["onboarding_state"] == "collecting"  # join handled
    assert db_row(tmp_path, "@quiet")["onboarding_state"] == "guided"       # nudge NOT consumed


def test_lock_prevents_overlapping_runs(tmp_path, monkeypatch):
    import fcntl

    make_profile(tmp_path)
    seed_state(tmp_path)
    (tmp_path / "ace" / "onboarding_tick.lock").parent.mkdir(exist_ok=True)
    holder = open(tmp_path / "ace" / "onboarding_tick.lock", "w")
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)                      # simulate a run mid-flight
    fakes = FakeAPIs(members=[{"user": {"id": "77", "username": "newbie"}, "roles": []}])
    out = run_tick(tmp_path, monkeypatch, fakes)
    assert json.loads(out) == {"wakeAgent": False}
    assert db_row(tmp_path, "@newbie") is None                              # skipped entirely
    holder.close()


def test_watchdog_starts_and_stops_listener(tmp_path, monkeypatch):
    import subprocess as sp

    make_profile(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "ace-join-listener.py").write_text("# listener", encoding="utf-8")
    spawned = []
    monkeypatch.setattr(sp, "Popen", lambda cmd, **kw: spawned.append(cmd) or type("P", (), {"pid": 999})())
    tick.ensure_listener(tmp_path, True)
    assert spawned and "ace-join-listener.py" in spawned[0][1]

    killed = []
    (tmp_path / "ace").mkdir(exist_ok=True)
    (tmp_path / "ace" / "onboarding_listener.pid").write_text("4242", encoding="utf-8")
    real_kill = tick.os.kill
    monkeypatch.setattr(tick.os, "kill", lambda pid, sig: killed.append((pid, sig)) if pid == 4242 else real_kill(pid, sig))
    tick.ensure_listener(tmp_path, False)                                   # switch off → stop it
    assert (4242, 15) in killed
