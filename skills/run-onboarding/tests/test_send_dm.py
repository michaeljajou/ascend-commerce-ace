"""send_dm.py: post-completion outreach respects the engagement policy."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import send_dm  # noqa: E402

from _lib import store  # noqa: E402
from _lib.models import Creator  # noqa: E402


def test_disabled_engagement_refuses_before_token_or_discord_read(tmp_path, monkeypatch, capsys):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(
        json.dumps({"features": {"engagement": False}}), encoding="utf-8"
    )
    monkeypatch.setattr(send_dm, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert send_dm.main(["--profile-dir", str(tmp_path), "--user-id", "123",
                         "--text", "Come back"]) == 0
    assert json.loads(capsys.readouterr().out) == {"disabled": "engagement"}


def test_engagement_dm_requires_a_guided_creator_record(tmp_path, monkeypatch, capsys):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({
        "features": {"engagement": True},
        "onboarding": {"enabled": True},
    }), encoding="utf-8")
    monkeypatch.setattr(send_dm, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert send_dm.main(["--profile-dir", str(tmp_path), "--user-id", "unknown",
                         "--text", "Come back"]) == 1
    assert "guided creator" in capsys.readouterr().err


def test_engagement_dm_allows_a_guided_completed_creator(tmp_path, monkeypatch):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({
        "features": {"engagement": True},
        "onboarding": {"enabled": True},
    }), encoding="utf-8")
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    conn = store.connect(ace_dir / "ace.db")
    store.upsert_creator(conn, Creator(
        handle="@guided", tiktok="guided.tt", role="creator", onboarding_state="guided"
    ))
    store.update_onboarding(conn, "@guided", discord_id="123")
    conn.close()
    sent = []
    monkeypatch.setattr(send_dm, "post",
                        lambda token, path, payload: sent.append(path) or {"id": "dm1"})

    assert send_dm.main(["--profile-dir", str(tmp_path), "--user-id", "123",
                         "--text", "Come back"]) == 0
    assert sent == ["/users/@me/channels", "/channels/dm1/messages"]
