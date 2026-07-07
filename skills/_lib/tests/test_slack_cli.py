"""slack_cli.py: brand-tagged outbound Slack posting."""

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import slack_cli  # noqa: E402


def make_profile(tmp_path, *, slack_channel="#ace-escalations", brand_name="Glow Labs"):
    ace = {"brand_id": "test-brand", "brand_name": brand_name, "slack_channel": slack_channel}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"ace": ace}), encoding="utf-8")
    (tmp_path / ".env").write_text("SLACK_BOT_TOKEN=xoxb-test\n", encoding="utf-8")
    return tmp_path


def run(tmp_path, monkeypatch, argv, api_result=None):
    calls = {}

    def fake_post(token, channel, text):
        calls.update(token=token, channel=channel, text=text)
        return api_result or {"ok": True, "ts": "1.23"}

    monkeypatch.setattr(slack_cli, "post_message", fake_post)
    monkeypatch.setenv("ACE_DATA_DIR", str(tmp_path / "ace"))
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    rc = slack_cli.main(argv)
    return rc, calls


def test_post_is_brand_tagged_to_configured_channel(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path)
    rc, calls = run(tmp_path, monkeypatch,
                    ["post", "--text", "creator @x needs help with a broken sample link"])
    assert rc == 0
    assert calls["channel"] == "#ace-escalations"
    assert calls["text"] == "[Glow Labs] creator @x needs help with a broken sample link"
    assert calls["token"] == "xoxb-test"                    # read from profile .env
    assert json.loads(capsys.readouterr().out)["brand_tag"] == "Glow Labs"


def test_channel_default_when_config_missing_it(tmp_path, monkeypatch):
    make_profile(tmp_path, slack_channel=None)
    rc, calls = run(tmp_path, monkeypatch, ["post", "--text", "hi"])
    assert rc == 0
    assert calls["channel"] == slack_cli.DEFAULT_CHANNEL


def test_explicit_channel_override(tmp_path, monkeypatch):
    make_profile(tmp_path)
    rc, calls = run(tmp_path, monkeypatch, ["post", "--channel", "#ops", "--text", "hi"])
    assert calls["channel"] == "#ops"


def test_slack_api_error_is_surfaced(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path)
    rc, _ = run(tmp_path, monkeypatch, ["post", "--text", "hi"],
                api_result={"ok": False, "error": "not_in_channel"})
    assert rc == 1
    assert "not_in_channel" in capsys.readouterr().err


def test_missing_token_errors(tmp_path, monkeypatch):
    make_profile(tmp_path)
    (tmp_path / ".env").write_text("OTHER=1\n", encoding="utf-8")
    monkeypatch.setenv("ACE_DATA_DIR", str(tmp_path / "ace"))
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    assert slack_cli.main(["post", "--text", "hi"]) == 1


def test_ace_prefixed_token_wins(tmp_path, monkeypatch):
    """ACE_SLACK_BOT_TOKEN keeps the Hermes gateway from thinking brands run Slack."""
    make_profile(tmp_path)
    (tmp_path / ".env").write_text("ACE_SLACK_BOT_TOKEN=xoxb-ace\nSLACK_BOT_TOKEN=xoxb-old\n",
                                   encoding="utf-8")
    rc, calls = run(tmp_path, monkeypatch, ["post", "--text", "hi"])
    assert rc == 0 and calls["token"] == "xoxb-ace"
