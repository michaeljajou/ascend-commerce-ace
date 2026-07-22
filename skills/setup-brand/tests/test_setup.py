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
    assert cfg["slack_channel"] == "#ace-escalations"   # shared all-brands default
    monkeypatch.setenv("ACE_DEFAULT_SLACK_CHANNEL", "#ace-ops")
    assert setup.build_config(spec)["slack_channel"] == "#ace-ops"   # env/root config wins over default


def test_merge_config_preserves_hermes_keys(tmp_path):
    import yaml

    cfg = tmp_path / "config.yaml"
    cfg.write_text("skills:\n  external_dirs:\n    - /repo/skills\n", encoding="utf-8")
    setup.merge_config(cfg, make_spec())
    data = yaml.safe_load(cfg.read_text())
    assert data["skills"]["external_dirs"] == ["/repo/skills"]       # PRESERVED, not clobbered
    assert data["ace"]["brand_id"] == "pilot"                       # ace config merged in
    assert data["model"] == "anthropic/claude-sonnet-4-6"           # answer model at top-level (spec had one)


def test_merge_config_sets_quiet_display_defaults(tmp_path):
    import yaml

    cfg = tmp_path / "config.yaml"
    setup.merge_config(cfg, make_spec())
    display = yaml.safe_load(cfg.read_text())["display"]
    assert display["tool_progress"] == "off"            # no tool breadcrumbs in client chat
    assert display["interim_assistant_messages"] is False  # no mid-turn notes


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
    assert jobs["daily-digest"]["deliver"] is None   # digest posts via slack_cli.py itself
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


def test_build_config_home_channel_default_and_override():
    cfg = setup.build_config(make_spec())
    assert cfg["discord"]["home_channel"] == "agent-ace"       # bundle default
    spec = make_spec()
    spec["discord"]["home_channel"] = "ops-ace"
    assert setup.build_config(spec)["discord"]["home_channel"] == "ops-ace"


def test_render_soul_has_clickable_channel_rule():
    assert "<#" in setup.render_soul(make_spec())              # the clickable-tag rule survived .format()


def test_write_profile_preserves_channel_directory_block(tmp_path):
    setup.write_profile(make_spec(), tmp_path)
    soul_path = tmp_path / "SOUL.md"
    block = "\n".join([
        setup.CHANNEL_DIR_START,
        "## Channel directory (auto-generated — do not edit)",
        "- #general → <#111>",
        setup.CHANNEL_DIR_END,
    ])
    soul_path.write_text(setup.upsert_channel_directory(soul_path.read_text(), block))
    setup.write_profile(make_spec(), tmp_path)                 # re-run regenerates SOUL.md ...
    text = soul_path.read_text()
    assert "- #general → <#111>" in text                       # ... but keeps the live directory
    assert text.count(setup.CHANNEL_DIR_START) == 1            # exactly once (no duplication)


def test_upsert_channel_directory_replaces_in_place():
    old = "# Soul\n\n" + setup.CHANNEL_DIR_START + "\nold\n" + setup.CHANNEL_DIR_END + "\n"
    new_block = setup.CHANNEL_DIR_START + "\nnew\n" + setup.CHANNEL_DIR_END
    out = setup.upsert_channel_directory(old, new_block)
    assert "old" not in out and "new" in out
    assert out.count(setup.CHANNEL_DIR_START) == 1


def test_build_config_sweep_and_team_role():
    cfg = setup.build_config(make_spec())
    assert cfg["discord"]["sweep_minutes"] == 5              # default grace window
    assert cfg["discord"]["team_role"] == "Ascend Team"      # bundle default, all brands
    spec = make_spec()
    spec["discord"]["team_role"] = "Other Team"
    spec["discord"]["sweep_minutes"] = 10
    cfg = setup.build_config(spec)
    assert cfg["discord"]["team_role"] == "Other Team"
    assert cfg["discord"]["sweep_minutes"] == 10


def test_build_cronjobs_includes_zero_token_sweep():
    jobs = {j["name"]: j for j in setup.build_cronjobs(make_spec())}
    sweep = jobs["sweep-unanswered"]
    assert sweep["schedule"] == "every 2m"
    assert sweep["script"] == "ace-sweep.py"                 # pre-script gates the agent
    assert sweep["skill"] == "sweep-unanswered"


def test_write_profile_installs_sweep_script(tmp_path):
    setup.write_profile(make_spec(), tmp_path)
    installed = tmp_path / "scripts" / "ace-sweep.py"
    assert installed.exists()
    assert "wakeAgent" in installed.read_text()              # the silent-tick gate is in place


def test_merge_config_sets_eastern_timezone_default(tmp_path):
    import yaml

    cfg = tmp_path / "config.yaml"
    setup.merge_config(cfg, make_spec())
    assert yaml.safe_load(cfg.read_text())["timezone"] == "America/New_York"
    cfg.write_text(yaml.safe_dump({"timezone": "Europe/London"}), encoding="utf-8")
    setup.merge_config(cfg, make_spec())
    assert yaml.safe_load(cfg.read_text())["timezone"] == "Europe/London"   # override survives


def test_build_onboarding_defaults_and_master_switch():
    ob = setup.build_onboarding(make_spec())
    assert ob["enabled"] is False                            # inert until the operator flips it
    assert ob["staff_role"] == "Ascend Team"
    assert ob["creator_roles"] == ["onboarded", "creator"]   # Vaulty parity: both roles
    assert (ob["nudge_hours"], ob["escalate_days"], ob["max_retries"]) == (48, 7, 3)
    assert ob["test_mode"] is False
    spec = make_spec(onboarding={"enabled": True, "nudge_hours": 24, "creator_roles": ["VIP"],
                                 "welcome_message": "hi {mention}"})
    ob = setup.build_onboarding(spec)
    assert ob["enabled"] is True and ob["nudge_hours"] == 24
    assert ob["creator_roles"] == ["VIP"] and ob["welcome_message"] == "hi {mention}"


def test_build_cronjobs_includes_onboarding_tick():
    jobs = {j["name"]: j for j in setup.build_cronjobs(make_spec())}
    job = jobs["onboarding-tick"]
    assert job["script"] == "ace-onboarding-tick.py"         # zero-token pre-script gates the agent
    assert job["skill"] == "run-onboarding"


def test_write_profile_installs_both_tick_scripts(tmp_path):
    setup.write_profile(make_spec(), tmp_path)
    assert (tmp_path / "scripts" / "ace-sweep.py").exists()
    assert (tmp_path / "scripts" / "ace-onboarding-tick.py").exists()


def test_merge_config_preserves_onboarding_channel_id(tmp_path):
    import yaml

    cfg = tmp_path / "config.yaml"
    setup.merge_config(cfg, make_spec())
    data = yaml.safe_load(cfg.read_text())
    data["ace"]["onboarding"]["channel_id"] = "900"          # written post-connect by resolve_channels
    cfg.write_text(yaml.safe_dump(data), encoding="utf-8")
    setup.merge_config(cfg, make_spec())                     # spec-driven re-run
    assert yaml.safe_load(cfg.read_text())["ace"]["onboarding"]["channel_id"] == "900"


def test_merge_config_locks_discord_to_the_minimal_toolset(tmp_path):
    """Every extra tool is another LLM round trip = creator-visible latency."""
    import yaml

    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"platform_toolsets": {
        "discord": ["web", "terminal", "clarify", "cronjob", "delegation", "browser", "memory"],
        "cli": ["web", "terminal", "clarify", "cronjob"],
    }}), encoding="utf-8")
    setup.merge_config(cfg, make_spec())
    data = yaml.safe_load(cfg.read_text())
    assert data["platform_toolsets"]["discord"] == setup.BRAND_DISCORD_TOOLSET
    assert "terminal" not in data["platform_toolsets"]["discord"]
    assert "delegation" not in data["platform_toolsets"]["discord"]   # the 6-minute replies
    assert "clarify" not in data["platform_toolsets"]["discord"]      # "Hermes needs your input"
    assert data["platform_toolsets"]["cli"] == ["web", "cronjob"]     # cli keeps its own tools
    display = data["display"]
    assert display["file_mutation_verifier"] is False
    assert display["turn_completion_explainer"] is False
    assert display["credits_notices"] is False


def test_merge_config_caps_turns_and_disables_curator(tmp_path):
    import yaml

    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"agent": {"max_turns": 150, "gateway_timeout": 900},
                                   "curator": {"enabled": True, "interval_hours": 168}}),
                   encoding="utf-8")
    setup.merge_config(cfg, make_spec())
    data = yaml.safe_load(cfg.read_text())
    assert data["agent"]["max_turns"] == 8                  # 150 round trips -> 8
    assert data["agent"]["gateway_timeout"] == 900          # other agent keys preserved
    assert data["curator"]["enabled"] is False              # no background skill rewrites
    assert data["curator"]["interval_hours"] == 168         # rest of curator config intact


def test_build_onboarding_carries_sheet_webhook():
    spec = make_spec(onboarding={"enabled": True, "sheet_webhook": "https://script.google.com/x"})
    assert setup.build_onboarding(spec)["sheet_webhook"] == "https://script.google.com/x"
    assert "sheet_webhook" not in setup.build_onboarding(make_spec())
