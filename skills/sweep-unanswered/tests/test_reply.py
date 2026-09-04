"""reply.py: deterministic Discord reply delivery."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reply  # noqa: E402


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
