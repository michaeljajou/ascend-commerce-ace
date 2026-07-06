"""get-campaigns fetch.py: newest channel post = the active campaign/challenge."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch  # noqa: E402


def make_profile(tmp_path, channels=("campaigns", "challenges")):
    (tmp_path / "channel_directory.json").write_text(json.dumps({
        "platforms": {"discord": [
            {"id": str(100 + i), "name": name, "type": "channel"}
            for i, name in enumerate(channels)
        ]}
    }), encoding="utf-8")
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok123\n", encoding="utf-8")
    return tmp_path


def msg(content, author="team", ts="2026-07-01T00:00:00Z"):
    return {"content": content, "author": {"username": author}, "timestamp": ts}


def test_summarize_newest_is_active_and_skips_empty():
    out = fetch.summarize([                       # Discord returns newest first
        msg("", ts="2026-07-06T00:00:00Z"),       # attachment-only → skipped
        msg("July Glow Challenge — post by 7/20, $500 prize", ts="2026-07-05T00:00:00Z"),
        msg("June campaign (over)", ts="2026-06-01T00:00:00Z"),
    ])
    assert out["active"]["content"].startswith("July Glow Challenge")
    assert [p["content"] for p in out["previous"]] == ["June campaign (over)"]


def test_summarize_empty_channel_means_no_active():
    assert fetch.summarize([]) == {"active": None, "previous": []}


def test_main_fetches_per_channel(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    calls = {}

    def fake_fetch(token, channel_id, limit):
        calls[channel_id] = (token, limit)
        return [msg(f"active in {channel_id}"), msg("older")]

    monkeypatch.setattr(fetch, "fetch_messages", fake_fetch)
    assert fetch.main(["--profile-dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["channels"]["campaigns"]["active"]["content"] == "active in 100"
    assert out["channels"]["challenges"]["active"]["content"] == "active in 101"
    assert out["missing_channels"] == []
    assert calls["100"] == ("tok123", 10)          # token read from profile .env; default limit


def test_main_reports_missing_channels(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path, channels=("campaigns",))   # no #challenges in this server
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setattr(fetch, "fetch_messages", lambda *a: [msg("hi")])
    assert fetch.main(["--profile-dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["missing_channels"] == ["challenges"]


def test_main_errors_without_token(tmp_path, monkeypatch):
    make_profile(tmp_path)
    (tmp_path / ".env").write_text("OTHER=1\n", encoding="utf-8")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    assert fetch.main(["--profile-dir", str(tmp_path)]) == 1


def test_main_errors_without_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
    assert fetch.main(["--profile-dir", str(tmp_path)]) == 1


def test_summarize_skips_bot_authors():
    """Ace's own reply in the channel must never become the 'active' campaign."""
    out = fetch.summarize([
        {"content": "Love this! Happy to help!", "author": {"username": "ace", "bot": True},
         "timestamp": "2026-07-03T15:42:32Z"},
        msg("JUNE PERFORMANCE INCENTIVE CAMPAIGN", author="nimam_9", ts="2026-07-03T15:42:15Z"),
    ])
    assert out["active"]["content"] == "JUNE PERFORMANCE INCENTIVE CAMPAIGN"
    assert all("Love this" not in p["content"] for p in out["previous"])
