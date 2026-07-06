"""sweep.py: zero-token candidate selection — wake the agent only for unanswered creators."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sweep  # noqa: E402

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
FIVE = timedelta(minutes=5)


def msg(mid, content, *, author_id="creator1", username=None, bot=False,
        minutes_ago=10, mentions=(), webhook=False):
    m = {
        "id": str(mid),
        "content": content,
        "author": {"id": author_id, "username": username or author_id, "bot": bot},
        "timestamp": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "mentions": [{"id": u} for u in mentions],
    }
    if webhook:
        m["webhook_id"] = "wh1"
    return m


def pick(messages, team_ids=frozenset(), bot_user_id="ace-bot"):
    return sweep.select_candidates(messages, now=NOW, threshold=FIVE,
                                   team_ids=set(team_ids), bot_user_id=bot_user_id)


def test_unanswered_creator_message_is_candidate():
    cands, last = pick([msg(1, "when do samples ship?", minutes_ago=10)])
    assert [c["id"] for c in cands] == ["1"]
    assert last == "1"


def test_team_role_author_is_never_a_candidate():
    cands, last = pick([msg(1, "CAMPAIGN LAUNCH 🔥", author_id="team1", minutes_ago=30)],
                       team_ids={"team1"})
    assert cands == [] and last == "1"


def test_team_reply_after_question_suppresses_it():
    cands, _ = pick([
        msg(1, "when do samples ship?", minutes_ago=10),
        msg(2, "they ship Friday!", author_id="team1", minutes_ago=8),
    ], team_ids={"team1"})
    assert cands == []


def test_bot_reply_counts_as_answered():
    """Ace's own instant @mention reply means the earlier message is handled."""
    cands, _ = pick([
        msg(1, "when do samples ship?", minutes_ago=10),
        msg(2, "Samples ship Fridays!", author_id="ace", bot=True, minutes_ago=9),
    ])
    assert cands == []


def test_mention_of_ace_is_skipped():
    """@Ace messages were answered live by the gateway — never sweep them."""
    cands, last = pick([msg(1, "hey @Ace when do samples ship?", minutes_ago=10,
                            mentions=("ace-bot",))])
    assert cands == [] and last == "1"


def test_young_message_stays_pending():
    """Inside the grace window: not a candidate yet, and last_seen must NOT advance."""
    cands, last = pick([msg(1, "when do samples ship?", minutes_ago=2)])
    assert cands == [] and last is None


def test_young_message_answered_next_tick_if_still_unanswered():
    old = msg(1, "when do samples ship?", minutes_ago=6)
    cands, last = pick([old])
    assert [c["id"] for c in cands] == ["1"] and last == "1"


def test_webhook_and_empty_messages_ignored():
    cands, last = pick([
        msg(1, "auto-post", webhook=True, minutes_ago=10),
        msg(2, "", minutes_ago=10),
    ])
    assert cands == [] and last == "2"


def test_creator_chatter_after_question_does_not_answer_it():
    cands, _ = pick([
        msg(1, "when do samples ship?", minutes_ago=10),
        msg(2, "same question here!", author_id="creator2", minutes_ago=7),
    ])
    assert [c["id"] for c in cands] == ["1", "2"]


# ── main(): wiring, state, and the silent-tick gate ────────────────────────────

def make_profile(tmp_path, *, team_role="Team"):
    import yaml
    ace = {"brand_id": "pilot", "discord": {
        "guild_id": "g1",
        "channels": {"community-chat": "FULL_ACTIVE"},
        "scoping": {"free_response": ["community-chat"], "ignored": [], "monitor": [],
                    "post_targets": []},
        "sweep_minutes": 5,
    }}
    if team_role:
        ace["discord"]["team_role"] = team_role
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"ace": ace}), encoding="utf-8")
    (tmp_path / "channel_directory.json").write_text(json.dumps({
        "platforms": {"discord": [{"id": "555", "name": "community-chat", "type": "channel"}]}
    }), encoding="utf-8")
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    return tmp_path


def fake_api(responses):
    """Dispatch _get(path) by prefix match against a dict of path→payload."""
    def _fake(token, path):
        for prefix, payload in responses.items():
            if path.startswith(prefix):
                return payload
        raise AssertionError(f"unexpected API call: {path}")
    return _fake


def run(tmp_path, monkeypatch, capsys, responses):
    monkeypatch.setattr(sweep, "_get", fake_api(responses))
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    rc = sweep.main(["--profile-dir", str(tmp_path)])
    assert rc == 0
    return capsys.readouterr().out.strip()


def test_first_run_initializes_without_backfill(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path)
    out = run(tmp_path, monkeypatch, capsys, {
        "/users/@me": {"id": "ace-bot"},
        "/guilds/g1/roles": [{"id": "r1", "name": "Team"}],
        "/channels/555/messages?limit=1": [msg(100, "old history", minutes_ago=999)],
    })
    assert json.loads(out) == {"wakeAgent": False}          # silent tick, zero tokens
    state = json.loads((tmp_path / "ace" / "sweep_state.json").read_text())
    assert state["channels"]["555"] == "100"                # anchored to now, no backfill
    assert state["team_role_id"] == "r1"


def test_second_run_surfaces_unanswered_and_advances_state(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path)
    (tmp_path / "ace").mkdir()
    (tmp_path / "ace" / "sweep_state.json").write_text(json.dumps({
        "channels": {"555": "100"}, "members": {},
        "bot_user_id": "ace-bot", "team_role_id": "r1",
    }))
    out = run(tmp_path, monkeypatch, capsys, {
        "/channels/555/messages?after=100": [
            msg(101, "how do I join the challenge?", author_id="creator1", minutes_ago=7),
            msg(102, "CAMPAIGN UPDATE", author_id="team1", minutes_ago=30),  # team post, own thread
        ],
        "/guilds/g1/members/creator1": {"roles": []},
        "/guilds/g1/members/team1": {"roles": ["r1"]},
    })
    payload = json.loads(out)
    surfaced = payload["unanswered_creator_messages"]
    assert [c["message_id"] for c in surfaced] == ["101"]   # creator surfaced, team post not
    assert surfaced[0]["channel"] == "community-chat"
    state = json.loads((tmp_path / "ace" / "sweep_state.json").read_text())
    assert state["channels"]["555"] == "102"                # consumed both
    assert state["members"]["team1"]["team"] is True        # membership cached


def test_no_new_messages_is_silent(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path)
    (tmp_path / "ace").mkdir()
    (tmp_path / "ace" / "sweep_state.json").write_text(json.dumps({
        "channels": {"555": "100"}, "members": {},
        "bot_user_id": "ace-bot", "team_role_id": "r1",
    }))
    out = run(tmp_path, monkeypatch, capsys, {"/channels/555/messages?after=100": []})
    assert json.loads(out) == {"wakeAgent": False}


def test_unwired_profile_is_silent_not_fatal(tmp_path, monkeypatch, capsys):
    (tmp_path / "config.yaml").write_text("ace: {}\n", encoding="utf-8")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    assert sweep.main(["--profile-dir", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out.strip()) == {"wakeAgent": False}
