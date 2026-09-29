"""send_dm.py: post-completion outreach respects the engagement policy."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import send_dm  # noqa: E402

from _lib import store  # noqa: E402
from _lib.models import Creator  # noqa: E402

# General Q&A disabled with engagement enabled. Setup rejects this combination, so only a
# hand-edited profile has it; the guided-creator guard is what limits outreach there.
RESTRICTED_WITH_ENGAGEMENT = {"general_qa": False, "engagement": True}


def write_sidecar(tmp_path, ace_config):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps(ace_config), encoding="utf-8")
    return ace_dir


def record_posts(monkeypatch):
    sent = []
    monkeypatch.setattr(send_dm, "post",
                        lambda token, path, payload: sent.append(path) or {"id": "dm1"})
    return sent


@pytest.mark.parametrize("ace_config,creator", [
    ({}, None),                                                        # no record at all
    ({"onboarding": {"enabled": True}}, None),
    ({"onboarding": {"enabled": True}}, {"onboarding_state": "collecting"}),
    ({"onboarding": {"enabled": True}}, {"onboarding_state": "active", "tiktok": "a.tt",
                                         "role": "creator"}),
    ({"onboarding": {"enabled": True}}, {"onboarding_state": "nudged", "tiktok": "a.tt",
                                         "role": "creator"}),          # unfinished rejoiner
    ({"onboarding": {"enabled": False}}, {"onboarding_state": "pre_existing"}),
    ({"features": {"engagement": True}, "onboarding": {"enabled": False}}, None),
    ({"features": {"reporting": False}}, None),
], ids=["no-config", "unknown-user", "collecting", "active", "nudged-unfinished",
        "onboarding-disabled", "explicit-engagement", "another-feature-disabled"])
def test_a_general_qa_brand_sends_every_dm_main_sent(tmp_path, monkeypatch, ace_config, creator):
    """**The bug this test exists for.** ENG-299 agent review round 6 (29 Sep 2026): the
    guard written for restricted profiles ran on every profile. `main` sent any DM it was
    asked to send. A brand with general Q&A and engagement enabled was refused a DM to a
    creator who was still collecting, already active, or unknown to the store, and any DM
    while onboarding was disabled, which is how a brand without onboarding nudges its
    creators and how the team sends an ad-hoc nudge."""
    ace_dir = write_sidecar(tmp_path, ace_config)
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    if creator:
        conn = store.connect(ace_dir / "ace.db")
        store.upsert_creator(conn, Creator(handle="@ava", **creator))
        store.update_onboarding(conn, "@ava", discord_id="123")
        conn.close()
    sent = record_posts(monkeypatch)

    assert send_dm.main(["--profile-dir", str(tmp_path), "--user-id", "123",
                         "--text", "Come say hi"]) == 0
    assert sent == ["/users/@me/channels", "/channels/dm1/messages"]


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
        "features": RESTRICTED_WITH_ENGAGEMENT,
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
        "features": RESTRICTED_WITH_ENGAGEMENT,
        "onboarding": {"enabled": True},
    }), encoding="utf-8")
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    conn = store.connect(ace_dir / "ace.db")
    store.upsert_creator(conn, Creator(
        handle="@guided", tiktok="guided.tt", role="creator", onboarding_state="guided"
    ))
    # guided() always stamps guided_at; a guided row without it is not a real shape.
    store.update_onboarding(conn, "@guided", discord_id="123", guided_at="210.0")
    conn.close()
    sent = []
    monkeypatch.setattr(send_dm, "post",
                        lambda token, path, payload: sent.append(path) or {"id": "dm1"})

    assert send_dm.main(["--profile-dir", str(tmp_path), "--user-id", "123",
                         "--text", "Come back"]) == 0
    assert sent == ["/users/@me/channels", "/channels/dm1/messages"]


def test_engagement_dm_refuses_a_rejoiner_nudged_before_finishing(
        tmp_path, monkeypatch, capsys):
    """**The bug this test exists for.** Found in review of the ENG-299 rejoin fix (28 Sep
    2026): this guard read a stored tiktok and role as completion. onboarding_tick keeps
    both when a creator rejoins, and moves a returning creator who never replied to
    nudged with no guided_at. They passed as a guided creator, so an engagement DM was
    permitted to someone who had not finished onboarding again."""
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({
        "features": RESTRICTED_WITH_ENGAGEMENT,
        "onboarding": {"enabled": True},
    }), encoding="utf-8")
    conn = store.connect(ace_dir / "ace.db")
    store.upsert_creator(conn, Creator(
        handle="@back", tiktok="back.tt", role="Creator", onboarding_state="nudged"
    ))
    store.update_onboarding(conn, "@back", discord_id="123", nudged_at="300.0")
    conn.close()
    monkeypatch.setattr(send_dm, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert send_dm.main(["--profile-dir", str(tmp_path), "--user-id", "123",
                         "--text", "Come back"]) == 1
    assert "guided creator" in capsys.readouterr().err


def test_restricted_engagement_dm_requires_onboarding_enabled(tmp_path, monkeypatch, capsys):
    write_sidecar(tmp_path, {"features": RESTRICTED_WITH_ENGAGEMENT,
                             "onboarding": {"enabled": False}})
    monkeypatch.setattr(send_dm, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert send_dm.main(["--profile-dir", str(tmp_path), "--user-id", "123",
                         "--text", "Come back"]) == 1
    assert "onboarding is disabled" in capsys.readouterr().err


def test_onboarding_only_profile_sends_no_dm(tmp_path, monkeypatch, capsys):
    write_sidecar(tmp_path, {
        "features": {name: False for name in
                     ("general_qa", "moderation", "announcements", "engagement", "reporting")},
        "onboarding": {"enabled": True},
    })
    monkeypatch.setattr(send_dm, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert send_dm.main(["--profile-dir", str(tmp_path), "--user-id", "123",
                         "--text", "Come back"]) == 0
    assert json.loads(capsys.readouterr().out) == {"disabled": "engagement"}
