import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import setup  # noqa: E402


def make_spec(**overrides):
    spec = {
        "brand_id": "pilot",
        "brand_name": "Pilot Brand",
        "discord": {
            "guild_id": 123,
            "channels": {
                "announcements": "POST_ONLY",
                "campaigns": "POST_ANSWER",
                "community-chat": "FULL_ACTIVE",
                "success-stories": "MONITOR_ONLY",
                "our-products": "ANSWER",
                "content-inspo": "INACTIVE",
            },
        },
        "slack_channel": "#pilot-ops",
        "model": "anthropic/claude-sonnet-4-6",
    }
    spec.update(overrides)
    return spec


def test_validate_spec_requires_keys():
    with pytest.raises(ValueError):
        setup.validate_spec({"brand_id": "x"})


def test_validate_spec_rejects_bad_behavior():
    spec = make_spec()
    spec["discord"]["channels"]["weird"] = "NONSENSE"
    with pytest.raises(ValueError):
        setup.validate_spec(spec)


def test_channel_scoping_maps_behaviors():
    scoping = setup.channel_scoping(make_spec()["discord"]["channels"])
    assert scoping["free_response"] == ["campaigns", "community-chat", "our-products"]
    assert scoping["ignored"] == ["announcements", "content-inspo"]
    assert scoping["monitor"] == ["success-stories"]
    assert scoping["post_targets"] == ["announcements", "campaigns"]


def test_build_config_shape():
    cfg = setup.build_config(make_spec())
    assert cfg["brand_id"] == "pilot"
    assert cfg["discord"]["scoping"]["monitor"] == ["success-stories"]
    assert cfg["knowledge_file"] == "knowledge.yaml"
    assert cfg["slack_channel"] == "#pilot-ops"
    assert cfg["classify_model"]          # default applied
    assert "model" not in cfg             # answer model lives at Hermes top-level, not in the ace block
    assert "drive_folder" not in cfg


def test_model_and_slack_optional(monkeypatch):
    spec = make_spec()
    spec.pop("model")
    spec.pop("slack_channel")
    monkeypatch.delenv("ACE_DEFAULT_SLACK_CHANNEL", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    cfg = setup.build_config(spec)              # no model, no slack, no env
    assert "slack_channel" not in cfg          # omitted, not crashed
    monkeypatch.setenv("ACE_DEFAULT_SLACK_CHANNEL", "#ace-ops")
    assert setup.build_config(spec)["slack_channel"] == "#ace-ops"   # env default applied


def test_merge_config_preserves_hermes_keys(tmp_path):
    import yaml

    cfg = tmp_path / "config.yaml"
    cfg.write_text("skills:\n  external_dirs:\n    - /repo/skills\n", encoding="utf-8")
    setup.merge_config(cfg, make_spec())
    data = yaml.safe_load(cfg.read_text())
    assert data["skills"]["external_dirs"] == ["/repo/skills"]       # PRESERVED, not clobbered
    assert data["ace"]["brand_id"] == "pilot"                       # ace config merged in
    assert data["model"] == "anthropic/claude-sonnet-4-6"           # answer model at top-level (spec had one)


def test_merge_config_omits_model_when_unspecified(tmp_path):
    import yaml

    spec = make_spec()
    spec.pop("model")
    cfg = tmp_path / "config.yaml"
    setup.merge_config(cfg, spec)
    assert "model" not in yaml.safe_load(cfg.read_text())           # inherits Hermes' default


def test_render_soul_includes_voice_rules_and_channels():
    soul = setup.render_soul(make_spec())
    assert "Pilot Brand" in soul
    assert "Never fabricate" in soul
    assert "#community-chat: FULL_ACTIVE" in soul
    assert "#pilot-ops" in soul


def test_build_cronjobs_targets_post_channel():
    jobs = {j["name"]: j for j in setup.build_cronjobs(make_spec())}
    assert set(jobs) >= {"daily-digest", "nudge-inactive", "weekly-reminders"}
    assert "ingest-knowledge" not in jobs  # no ingest step with YAML knowledge
    assert jobs["daily-digest"]["deliver"] == "slack"
    assert jobs["weekly-reminders"]["deliver"] == "discord:#announcements"


def test_write_profile_roundtrips_config(tmp_path):
    import yaml

    written = setup.write_profile(make_spec(), tmp_path)
    cfg = yaml.safe_load(Path(written["config"]).read_text())
    assert cfg["ace"]["brand_id"] == "pilot"
    assert Path(written["soul"]).read_text().count("Ace") >= 1
    cron = json.loads(Path(written["cronjobs"]).read_text())
    assert any(j["skill"] == "daily-digest" for j in cron)


def test_write_profile_sets_ace_data_dir_in_env(tmp_path):
    written = setup.write_profile(make_spec(), tmp_path)
    env_text = Path(written["env"]).read_text()
    assert f"ACE_DATA_DIR={tmp_path.resolve() / 'ace'}" in env_text
    assert written["data_dir"] == str((tmp_path / "ace").resolve())


def test_ensure_env_preserves_existing_and_is_idempotent(tmp_path):
    (tmp_path / ".env").write_text("DISCORD_TOKEN=abc123\n", encoding="utf-8")
    setup.ensure_env(tmp_path, {"ACE_DATA_DIR": "/data/ace"})
    setup.ensure_env(tmp_path, {"ACE_DATA_DIR": "/data/ace"})  # again → no dup
    text = (tmp_path / ".env").read_text()
    assert "DISCORD_TOKEN=abc123" in text          # untouched
    assert text.count("ACE_DATA_DIR=") == 1        # idempotent
    assert "ACE_DATA_DIR=/data/ace" in text


def test_no_post_target_skips_weekly_reminders():
    spec = make_spec()
    spec["discord"]["channels"] = {"community-chat": "FULL_ACTIVE"}  # no POST_* channels
    names = {j["name"] for j in setup.build_cronjobs(spec)}
    assert "weekly-reminders" not in names
