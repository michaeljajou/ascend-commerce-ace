"""reply.py: deterministic Discord reply delivery."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reply  # noqa: E402

from _lib import store  # noqa: E402
from _lib.models import Creator  # noqa: E402


def test_posts_reply_with_reference_and_safe_mentions(tmp_path, monkeypatch, capsys):
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    sent = {}

    def fake_post(token, channel_id, text, reply_to):
        sent.update(token=token, channel_id=channel_id, text=text, reply_to=reply_to)
        return {"id": "999"}

    monkeypatch.setattr(reply, "post_reply", fake_post)
    rc = reply.main(["--profile-dir", str(tmp_path), "--channel-id", "555",
                     "--reply-to", "101", "--text", "Samples ship Fridays! See <#123>."])
    assert rc == 0
    assert sent == {"token": "tok", "channel_id": "555",
                    "text": "Samples ship Fridays! See <#123>.", "reply_to": "101"}
    assert json.loads(capsys.readouterr().out)["sent"] == "999"


def capture_post(monkeypatch):
    captured = {}

    class FakeResp:
        def read(self):
            return b'{"id": "1"}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode())
        captured["url"] = req.full_url
        return FakeResp()

    monkeypatch.setattr(reply.urllib.request, "urlopen", fake_urlopen)
    return captured


def test_payload_shape_never_pings_everyone(monkeypatch):
    captured = capture_post(monkeypatch)
    reply.post_reply("tok", "555", "hi @everyone", "101")
    assert captured["body"]["allowed_mentions"]["parse"] == ["users"]
    assert captured["body"]["message_reference"]["message_id"] == "101"
    assert captured["url"].endswith("/channels/555/messages")


def test_reply_pings_the_creator_it_answers(monkeypatch):
    """Discord defaults `replied_user` to false whenever allowed_mentions is supplied, so
    the two I Am Joy sweep replies (2026-08-28, 2026-09-03) notified nobody."""
    captured = capture_post(monkeypatch)
    reply.post_reply("tok", "555", "hi", "101")
    assert captured["body"]["allowed_mentions"]["replied_user"] is True


def test_empty_text_errors():
    assert reply.main(["--channel-id", "555", "--text", "  "]) == 1


# ── what the agent's shell did to the text (I Am Joy, 2026-08-28 / 2026-09-03) ──
# Both replies went through `--text "..."` in the terminal tool: bash keeps `\n` as two
# literal characters (the creator saw "\n\n" mid-message) and expands `$5` in "$50" to
# nothing (the creator read "a chance to win 0!"). The skill now hands the text over on
# stdin inside a quoted heredoc; reply.py still repairs the escape it can.

def test_literal_backslash_n_becomes_a_newline():
    assert reply.clean_text(r"first line.\n\nsecond line.") == "first line.\n\nsecond line."
    assert reply.clean_text("already\nreal") == "already\nreal"


def test_stdin_text_is_taken_verbatim(tmp_path, monkeypatch, capsys):
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("win $50 each!\n\nReply here.\n"))
    sent = {}
    monkeypatch.setattr(reply, "post_reply",
                        lambda token, cid, text, rt: sent.update(text=text) or {"id": "9"})
    assert reply.main(["--profile-dir", str(tmp_path), "--channel-id", "555",
                       "--reply-to", "101", "--stdin"]) == 0
    assert sent["text"] == "win $50 each!\n\nReply here."


# ── tagging the creator ───────────────────────────────────────────────────────
# "Hey tesh.oneal" is a bare username: no tag, no notification. The sweep payload now
# carries the author's id, and --mention guarantees the tag is in the message.

def test_mention_is_prepended_when_missing():
    assert reply.with_mention("Hey! Samples ship Fridays.", "42") == "<@42> Hey! Samples ship Fridays."


def test_mention_is_not_doubled_when_the_agent_already_tagged_them():
    assert reply.with_mention("Hey <@42> 👋 samples ship Fridays.", "42") == "Hey <@42> 👋 samples ship Fridays."


def test_main_applies_mention(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    sent = {}
    monkeypatch.setattr(reply, "post_reply",
                        lambda token, cid, text, rt: sent.update(text=text) or {"id": "9"})
    assert reply.main(["--profile-dir", str(tmp_path), "--channel-id", "555", "--reply-to", "101",
                       "--mention", "42", "--text", "Hey! Samples ship Fridays."]) == 0
    assert sent["text"] == "<@42> Hey! Samples ship Fridays."


def test_disabled_general_qa_refuses_support_reply_before_token_read(
        tmp_path, monkeypatch, capsys):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({
        "features": {"general_qa": False},
        "onboarding": {"enabled": True, "channel_id": "777"},
    }), encoding="utf-8")
    monkeypatch.setattr(reply, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert reply.main(["--profile-dir", str(tmp_path), "--channel-id", "555",
                       "--text", "Support answer"]) == 0
    assert json.loads(capsys.readouterr().out) == {"disabled": "general_qa"}


def test_onboarding_reply_requires_a_recorded_active_creator_thread(
        tmp_path, monkeypatch, capsys):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({
        "features": {"general_qa": False},
        "onboarding": {"enabled": True, "channel_id": "777"},
    }), encoding="utf-8")
    monkeypatch.setattr(reply, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "onboarding",
                       "--channel-id", "777", "--text", "Continue onboarding"]) == 1
    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "onboarding",
                       "--channel-id", "555", "--text", "Wrong channel"]) == 1
    assert "active creator onboarding thread" in capsys.readouterr().err


def test_onboarding_reply_allows_a_recorded_creator_thread(tmp_path, monkeypatch):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({
        "features": {"general_qa": False},
        "onboarding": {"enabled": True, "channel_id": "777"},
    }), encoding="utf-8")
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    conn = store.connect(ace_dir / "ace.db")
    store.upsert_creator(conn, Creator(handle="@new", onboarding_state="collecting"))
    store.update_onboarding(conn, "@new", thread_id="888")
    conn.close()
    sent = {}
    monkeypatch.setattr(reply, "post_reply",
                        lambda token, cid, text, rt: sent.update(channel=cid) or {"id": "9"})

    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "onboarding",
                       "--channel-id", "888", "--text", "Continue onboarding"]) == 0
    assert sent["channel"] == "888"


def test_onboarding_reply_refuses_a_completed_creator_thread(tmp_path, monkeypatch, capsys):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({
        "features": {"general_qa": False, "engagement": True},
        "onboarding": {"enabled": True, "channel_id": "777"},
    }), encoding="utf-8")
    conn = store.connect(ace_dir / "ace.db")
    store.upsert_creator(conn, Creator(
        handle="@done", tiktok="done.tt", role="creator", onboarding_state="guided"
    ))
    store.update_onboarding(conn, "@done", thread_id="999")
    conn.close()
    monkeypatch.setattr(reply, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "onboarding",
                       "--channel-id", "999", "--text", "Support answer"]) == 1
    assert "active creator onboarding thread" in capsys.readouterr().err


def seed_remembered_thread(tmp_path, state, guided_at=None):
    """A creator Ace already knows, in thread 888: fields and role stored, lifecycle set
    by the caller. A rejoin leaves exactly this with no guided_at."""
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({
        "features": {"general_qa": False, "engagement": True},
        "onboarding": {"enabled": True, "channel_id": "777"},
    }), encoding="utf-8")
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    conn = store.connect(ace_dir / "ace.db")
    store.upsert_creator(conn, Creator(
        handle="@back", tiktok="back.tt", role="Creator", onboarding_state=state
    ))
    store.update_onboarding(conn, "@back", thread_id="888", guided_at=guided_at)
    conn.close()


def test_onboarding_reply_allows_a_rejoined_creator_thread(tmp_path, monkeypatch):
    """**The bug this test exists for.** Found in review of the ENG-299 rejoin fix (28 Sep
    2026): this guard read a stored tiktok and role as completion. onboarding_tick keeps
    both when a creator rejoins and restarts the row at collecting, so an onboarding reply
    to a returning creator's new thread was refused as not an active onboarding thread."""
    seed_remembered_thread(tmp_path, "collecting")
    sent = {}
    monkeypatch.setattr(reply, "post_reply",
                        lambda token, cid, text, rt: sent.update(channel=cid) or {"id": "9"})

    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "onboarding",
                       "--channel-id", "888", "--text", "Welcome back"]) == 0
    assert sent["channel"] == "888"


def test_engagement_reply_refuses_a_rejoiner_nudged_before_finishing(
        tmp_path, monkeypatch, capsys):
    """**The bug this test exists for.** Same review: a returning creator who never replied
    is moved to nudged by the tick with the remembered tiktok and role and no guided_at.
    The guard read that as a guided creator and would have sent engagement outreach to
    someone still locked out of the server."""
    seed_remembered_thread(tmp_path, "nudged")
    monkeypatch.setattr(reply, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "engagement",
                       "--channel-id", "888", "--text", "Come back"]) == 1
    assert "guided creator thread" in capsys.readouterr().err


def test_engagement_reply_allows_a_guided_creator_thread(tmp_path, monkeypatch):
    seed_remembered_thread(tmp_path, "nudged", guided_at="210.0")
    sent = {}
    monkeypatch.setattr(reply, "post_reply",
                        lambda token, cid, text, rt: sent.update(channel=cid) or {"id": "9"})

    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "engagement",
                       "--channel-id", "888", "--text", "Come back"]) == 0
    assert sent["channel"] == "888"


def test_disabled_engagement_refuses_recorded_thread_nudge_before_token_read(
        tmp_path, monkeypatch, capsys):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({
        "features": {"general_qa": False, "engagement": False},
        "onboarding": {"enabled": True, "channel_id": "777"},
    }), encoding="utf-8")
    monkeypatch.setattr(reply, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "engagement",
                       "--channel-id", "888", "--text", "Come back"]) == 0
    assert json.loads(capsys.readouterr().out) == {"disabled": "engagement"}


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
], ids=["no-config", "unknown-thread", "collecting", "active", "nudged-unfinished",
        "onboarding-disabled", "explicit-engagement", "another-feature-disabled"])
def test_a_general_qa_brand_posts_every_engagement_reply_main_posted(
        tmp_path, monkeypatch, ace_config, creator):
    """**The bug this test exists for.** ENG-299 agent review round 7 (29 Sep 2026): the
    guard written for restricted profiles ran on every profile. This script is the thread
    fallback when a nudge cannot be sent by DM, and `main` posted whatever it was given.
    A brand with general Q&A and engagement enabled was refused the fallback for a creator
    who was active, collecting, or unknown to the store, and for anyone while onboarding
    was disabled, so a team nudge to a creator who blocks DMs reached nobody."""
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps(ace_config), encoding="utf-8")
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok\n", encoding="utf-8")
    if creator:
        conn = store.connect(ace_dir / "ace.db")
        store.upsert_creator(conn, Creator(handle="@ava", **creator))
        store.update_onboarding(conn, "@ava", thread_id="888")
        conn.close()
    sent = {}
    monkeypatch.setattr(reply, "post_reply",
                        lambda token, cid, text, rt: sent.update(channel=cid) or {"id": "9"})

    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "engagement",
                       "--channel-id", "888", "--text", "Come say hi"]) == 0
    assert sent["channel"] == "888"


def test_restricted_engagement_reply_requires_onboarding_enabled(tmp_path, monkeypatch, capsys):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({
        "features": {"general_qa": False, "engagement": True},
        "onboarding": {"enabled": False},
    }), encoding="utf-8")
    monkeypatch.setattr(reply, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "engagement",
                       "--channel-id", "888", "--text", "Come back"]) == 1
    assert "onboarding is disabled" in capsys.readouterr().err


def test_onboarding_reply_guard_applies_with_general_qa_enabled(tmp_path, monkeypatch, capsys):
    """The onboarding purpose did not exist on `main`, so its guard holds for every profile."""
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(json.dumps({"onboarding": {"enabled": True}}),
                                        encoding="utf-8")
    monkeypatch.setattr(reply, "bot_token",
                        lambda _profile: (_ for _ in ()).throw(AssertionError("token read")))

    assert reply.main(["--profile-dir", str(tmp_path), "--purpose", "onboarding",
                       "--channel-id", "555", "--text", "Wrong channel"]) == 1
    assert "active creator onboarding thread" in capsys.readouterr().err
