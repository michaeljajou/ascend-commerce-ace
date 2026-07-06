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


def test_payload_shape_never_pings_everyone(monkeypatch):
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
    reply.post_reply("tok", "555", "hi @everyone", "101")
    assert captured["body"]["allowed_mentions"] == {"parse": ["users"]}
    assert captured["body"]["message_reference"]["message_id"] == "101"
    assert captured["url"].endswith("/channels/555/messages")


def test_empty_text_errors():
    assert reply.main(["--channel-id", "555", "--text", "  "]) == 1
