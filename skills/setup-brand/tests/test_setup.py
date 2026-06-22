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
        "drive_folder": "folder-123",
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
    assert cfg["model"]["provider"] == "openrouter"
    assert cfg["model"]["default"] == "anthropic/claude-sonnet-4-6"
    assert cfg["model"]["classify"]  # default applied
    assert cfg["discord"]["scoping"]["monitor"] == ["success-stories"]
    assert cfg["drive_folder"] == "folder-123"


def test_render_soul_includes_voice_rules_and_channels():
    soul = setup.render_soul(make_spec())
    assert "Pilot Brand" in soul
    assert "Never fabricate" in soul
    assert "#community-chat: FULL_ACTIVE" in soul
    assert "#pilot-ops" in soul


def test_build_cronjobs_targets_post_channel():
    jobs = {j["name"]: j for j in setup.build_cronjobs(make_spec())}
    assert set(jobs) >= {"ingest-knowledge", "daily-digest", "nudge-inactive", "weekly-reminders"}
    assert jobs["daily-digest"]["deliver"] == "slack"
    assert jobs["weekly-reminders"]["deliver"] == "discord:#announcements"


def test_write_profile_roundtrips_config(tmp_path):
    written = setup.write_profile(make_spec(), tmp_path)
    cfg = json.loads(Path(written["config"]).read_text())
    assert cfg["brand_id"] == "pilot"
    assert Path(written["soul"]).read_text().count("Ace") >= 1
    cron = json.loads(Path(written["cronjobs"]).read_text())
    assert any(j["skill"] == "ingest-knowledge" for j in cron)


def test_no_post_target_skips_weekly_reminders():
    spec = make_spec()
    spec["discord"]["channels"] = {"community-chat": "FULL_ACTIVE"}  # no POST_* channels
    names = {j["name"] for j in setup.build_cronjobs(spec)}
    assert "weekly-reminders" not in names
