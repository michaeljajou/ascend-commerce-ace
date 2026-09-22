"""_lib/discord.py: the Discord REST bits every posting script needs."""

import json
from datetime import datetime, timedelta, timezone

from _lib import discord


def test_channel_slug_strips_decorations_and_guild_prefixes():
    assert discord.channel_slug("📢│announcements") == "announcements"
    assert discord.channel_slug("Brand / #campaigns") == "campaigns"
    assert discord.channel_slug("#Community-Chat") == "community-chat"
    assert discord.channel_slug("agent-ace") == "agent-ace"


def test_channel_ids_resolves_plain_names_against_decorated_directory(tmp_path):
    (tmp_path / "channel_directory.json").write_text(json.dumps({"platforms": {"discord": [
        {"id": "555", "name": "📢│announcements", "type": "channel"},
        {"id": "556", "name": "Brand / #campaigns", "type": "channel"},
        {"id": "999", "name": "Brand / #x", "type": "group"},
    ]}}), encoding="utf-8")
    found, missing = discord.channel_ids(tmp_path, ["announcements", "campaigns", "x", "nope"])
    assert found == {"announcements": "555", "campaigns": "556"}
    assert missing == ["x", "nope"]


def test_channel_ids_without_directory_names_the_fix(tmp_path):
    try:
        discord.channel_ids(tmp_path, ["announcements"])
    except FileNotFoundError as exc:
        assert "channel_directory.json" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_bot_token_prefers_env_then_profile_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    assert discord.bot_token(tmp_path) is None
    (tmp_path / ".env").write_text("X=1\nDISCORD_BOT_TOKEN='from-file'\n", encoding="utf-8")
    assert discord.bot_token(tmp_path) == "from-file"
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "from-env")
    assert discord.bot_token(tmp_path) == "from-env"


class FakeResp:
    def __init__(self, body):
        self._body = json.dumps(body).encode()
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_post_message_never_pings_anyone_by_default(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode())
        captured["auth"] = req.get_header("Authorization")
        return FakeResp({"id": "1"})

    monkeypatch.setattr(discord.urllib.request, "urlopen", fake_urlopen)
    assert discord.post_message("tok", "555", "hi @everyone <@&1>")["id"] == "1"
    assert captured["url"].endswith("/channels/555/messages")
    assert captured["method"] == "POST"
    assert captured["auth"] == "Bot tok"
    assert captured["body"]["content"] == "hi @everyone <@&1>"
    assert captured["body"]["allowed_mentions"] == {"parse": []}


def test_recent_own_post_finds_only_this_bots_message_inside_the_window(monkeypatch):
    now = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)
    stamp = lambda minutes_ago: (now - timedelta(minutes=minutes_ago)).isoformat()  # noqa: E731

    def fake_urlopen(req, timeout):
        if req.full_url.endswith("/users/@me"):
            return FakeResp({"id": "bot1"})
        return FakeResp([
            {"id": "m3", "author": {"id": "human", "bot": False}, "timestamp": stamp(1), "content": "hey"},
            {"id": "m2", "author": {"id": "other-bot", "bot": True}, "timestamp": stamp(2), "content": "x"},
            {"id": "m1", "author": {"id": "bot1", "bot": True}, "timestamp": stamp(30), "content": "ours"},
        ])

    monkeypatch.setattr(discord.urllib.request, "urlopen", fake_urlopen)
    hit = discord.recent_own_post("tok", "555", within_minutes=60, now=now)
    assert hit["id"] == "m1"
    assert discord.recent_own_post("tok", "555", within_minutes=10, now=now) is None
