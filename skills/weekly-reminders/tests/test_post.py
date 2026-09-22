"""post.py: the reminder reaches the brand's announcement channel by script, so the cron
job's own delivery (and therefore any failure summary) can stay in the private home channel."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import post  # noqa: E402

DIRECTORY = {"platforms": {"discord": [
    {"id": "555", "name": "📢│announcements", "type": "channel"},
    {"id": "556", "name": "Brand / #campaigns", "type": "channel"},
    {"id": "103", "name": "agent-ace", "type": "channel"},
]}}
BRAND = {"brand_id": "pilot", "discord": {"guild_id": "1", "channels": {
    "announcements": "POST_ONLY", "campaigns": "POST_ANSWER", "community-chat": "FULL_ACTIVE"}}}


def make_profile(tmp_path, brand=BRAND, directory=DIRECTORY):
    (tmp_path / "ace").mkdir()
    (tmp_path / "ace" / "brand.json").write_text(json.dumps(brand), encoding="utf-8")
    if directory is not None:
        (tmp_path / "channel_directory.json").write_text(json.dumps(directory), encoding="utf-8")
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    return tmp_path


def wire(monkeypatch, recent=None):
    sent = {}
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setattr(post, "recent_own_post", lambda token, channel_id, within_minutes: recent)

    def fake_post(token, channel_id, text):
        sent.update(token=token, channel_id=channel_id, text=text)
        return {"id": "999"}

    monkeypatch.setattr(post, "post_message", fake_post)
    return sent


def test_posts_to_the_brands_announcement_channel_and_reports_it(tmp_path, monkeypatch, capsys):
    """No channel argument: the target is the brand's POST_* channel from brand.json, resolved
    to its id through channel_directory.json — the agent never picks a channel."""
    make_profile(tmp_path)
    sent = wire(monkeypatch)
    rc = post.main(["--profile-dir", str(tmp_path), "--text", "🔥 September campaign ends Oct 2!"])
    assert rc == 0
    assert sent == {"token": "tok", "channel_id": "555", "text": "🔥 September campaign ends Oct 2!"}
    out = json.loads(capsys.readouterr().out)
    assert out == {"posted": "999", "channel": "announcements", "channel_id": "555"}


def test_stdin_heredoc_is_the_intended_path_and_literal_backslash_n_is_repaired(tmp_path, monkeypatch):
    """Same shell lesson as sweep's reply.py: bash keeps `\\n` verbatim inside double quotes."""
    make_profile(tmp_path)
    sent = wire(monkeypatch)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("Line one\\nLine two\n"))
    assert post.main(["--profile-dir", str(tmp_path), "--stdin"]) == 0
    assert sent["text"] == "Line one\nLine two"


def test_explicit_channel_id_skips_resolution(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path, directory=None)
    sent = wire(monkeypatch)
    assert post.main(["--profile-dir", str(tmp_path), "--channel-id", "777", "--text", "hi"]) == 0
    assert sent["channel_id"] == "777"
    assert json.loads(capsys.readouterr().out)["channel_id"] == "777"


def test_refuses_to_post_twice_in_one_window(tmp_path, monkeypatch, capsys):
    """An agent that retries after a slow tool call must not post the reminder twice. The
    guard is the bot's own newest message in the channel; --force is the operator's override."""
    make_profile(tmp_path)
    sent = wire(monkeypatch, recent={"id": "m1", "timestamp": "2026-09-24T19:55:00+00:00"})
    rc = post.main(["--profile-dir", str(tmp_path), "--text", "again"])
    assert rc == 2
    assert sent == {}
    assert "m1" in capsys.readouterr().err
    assert post.main(["--profile-dir", str(tmp_path), "--text", "again", "--force"]) == 0
    assert sent["text"] == "again"


def test_dry_run_resolves_everything_but_posts_nothing(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path)
    sent = wire(monkeypatch)
    assert post.main(["--profile-dir", str(tmp_path), "--text", "hi", "--dry-run"]) == 0
    assert sent == {}
    out = json.loads(capsys.readouterr().out)
    assert out == {"dry_run": True, "channel": "announcements", "channel_id": "555", "characters": 2}


def test_empty_and_oversized_text_are_refused(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path)
    sent = wire(monkeypatch)
    assert post.main(["--profile-dir", str(tmp_path), "--text", "   "]) == 1
    assert post.main(["--profile-dir", str(tmp_path), "--text", "x" * 2001]) == 1
    assert sent == {}
    assert "2000" in capsys.readouterr().err


def test_missing_directory_or_post_channel_is_a_clear_error(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path, directory=None)
    wire(monkeypatch)
    assert post.main(["--profile-dir", str(tmp_path), "--text", "hi"]) == 1
    assert "channel_directory.json" in capsys.readouterr().err

    no_post = {"brand_id": "p", "discord": {"guild_id": "1", "channels": {"community-chat": "FULL_ACTIVE"}}}
    (tmp_path / "b").mkdir()
    prof = make_profile(tmp_path / "b", brand=no_post)
    assert post.main(["--profile-dir", str(prof), "--text", "hi"]) == 1
    assert "POST_ONLY" in capsys.readouterr().err
