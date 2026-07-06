"""resolve_channels.py: post-connect wiring — free-response IDs, home channel, SOUL channel map."""

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import resolve_channels  # noqa: E402
import setup  # noqa: E402


def make_profile(tmp_path, *, home_channel=None, directory_channels=None, with_soul=True):
    """A minimal post-first-connect brand profile."""
    ace_discord = {
        "guild_id": "g1",
        "channels": {"campaigns": "POST_ANSWER", "community-chat": "FULL_ACTIVE"},
        "scoping": {"free_response": ["campaigns", "community-chat"], "ignored": [],
                    "monitor": [], "post_targets": ["campaigns"]},
    }
    if home_channel:
        ace_discord["home_channel"] = home_channel
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"ace": {"brand_id": "pilot", "discord": ace_discord}}), encoding="utf-8"
    )
    channels = directory_channels if directory_channels is not None else [
        {"id": "101", "name": "campaigns", "type": "channel"},
        {"id": "102", "name": "community-chat", "type": "channel"},
        {"id": "103", "name": "agent-ace", "type": "channel"},
        {"id": "999", "name": "Test / #x", "type": "group"},   # non-channel entries are skipped
    ]
    (tmp_path / "channel_directory.json").write_text(
        json.dumps({"platforms": {"discord": channels}}), encoding="utf-8"
    )
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=secret\n", encoding="utf-8")
    if with_soul:
        (tmp_path / "SOUL.md").write_text("# Ace — Pilot\n\n## Rules\n- Never fabricate.\n", encoding="utf-8")
    return tmp_path


def test_resolves_free_response_home_and_soul(tmp_path):
    make_profile(tmp_path)
    assert resolve_channels.main(["--profile-dir", str(tmp_path)]) == 0

    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert cfg["discord"]["free_response_channels"] == "101,102"
    assert cfg["discord"]["require_mention"] is True

    env = (tmp_path / ".env").read_text()
    assert "DISCORD_BOT_TOKEN=secret" in env                    # untouched
    assert "DISCORD_HOME_CHANNEL=103" in env                    # default #agent-ace resolved
    assert "DISCORD_HOME_CHANNEL_NAME=#agent-ace" in env

    soul = (tmp_path / "SOUL.md").read_text()
    assert setup.CHANNEL_DIR_START in soul
    assert "- #campaigns → <#101>" in soul
    assert "- #agent-ace → <#103>" in soul
    assert "#x" not in soul                                     # group entries excluded


def test_home_channel_spec_override(tmp_path):
    make_profile(tmp_path, home_channel="community-chat")
    resolve_channels.main(["--profile-dir", str(tmp_path)])
    env = (tmp_path / ".env").read_text()
    assert "DISCORD_HOME_CHANNEL=102" in env
    assert "DISCORD_HOME_CHANNEL_NAME=#community-chat" in env


def test_missing_home_channel_warns_but_succeeds(tmp_path, capsys):
    make_profile(tmp_path, directory_channels=[
        {"id": "101", "name": "campaigns", "type": "channel"},
        {"id": "102", "name": "community-chat", "type": "channel"},
    ])
    assert resolve_channels.main(["--profile-dir", str(tmp_path)]) == 0   # still wires the rest
    assert "home channel #agent-ace not found" in capsys.readouterr().err
    assert "DISCORD_HOME_CHANNEL=" not in (tmp_path / ".env").read_text()


def test_idempotent_rerun(tmp_path):
    make_profile(tmp_path)
    resolve_channels.main(["--profile-dir", str(tmp_path)])
    resolve_channels.main(["--profile-dir", str(tmp_path)])
    soul = (tmp_path / "SOUL.md").read_text()
    assert soul.count(setup.CHANNEL_DIR_START) == 1             # block replaced, not duplicated
    assert (tmp_path / ".env").read_text().count("DISCORD_HOME_CHANNEL=") == 1


def test_setup_rerun_keeps_soul_directory(tmp_path):
    """write_profile regenerates SOUL.md but must keep the live channel directory."""
    make_profile(tmp_path)
    resolve_channels.main(["--profile-dir", str(tmp_path)])
    spec = {"brand_id": "pilot", "brand_name": "Pilot",
            "discord": {"guild_id": "g1", "channels": {"campaigns": "POST_ANSWER"}}}
    setup.write_profile(spec, tmp_path)
    soul = (tmp_path / "SOUL.md").read_text()
    assert "- #campaigns → <#101>" in soul
    assert soul.count(setup.CHANNEL_DIR_START) == 1


def test_missing_directory_errors(tmp_path):
    (tmp_path / "config.yaml").write_text("ace: {}\n", encoding="utf-8")
    assert resolve_channels.main(["--profile-dir", str(tmp_path)]) == 1
