"""The agent's code sandbox has no third-party packages — prove the scripts survive it.

QA, 2026-07-22: every server-side check ran under Hermes' own interpreter, which has
PyYAML, so this was invisible until a creator hit it. `onboarding.py answer` died on
`import yaml`; the agent then tried `uv pip install`, `uv pip install --system`,
`apt-get install`, and finally built itself a venv — six tool calls and 112 seconds to
answer one message, and the creator was charged two retries for it.

These tests hide PyYAML from the import system, which is what the sandbox does in effect.
"""
import builtins
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import assign_role  # noqa: E402
import onboarding  # noqa: E402

from _lib import brand, slack_cli, store  # noqa: E402


@pytest.fixture
def no_pyyaml(monkeypatch):
    """Make `import yaml` raise ImportError, as it does in the agent's sandbox."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml" or name.startswith("yaml."):
            raise ImportError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(sys.modules, "yaml", raising=False)


@pytest.fixture
def profile(tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_DATA_DIR", str(tmp_path / "ace"))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    return tmp_path


def test_brand_config_reads_the_json_sidecar_without_pyyaml(profile, no_pyyaml):
    brand.write_sidecar(profile, {"brand_id": "glow", "discord": {"guild_id": "99"},
                                  "onboarding": {"creator_roles": ["onboarded", "creator"]}})
    cfg = brand.config(profile)
    assert cfg["discord"]["guild_id"] == "99"
    assert cfg["onboarding"]["creator_roles"] == ["onboarded", "creator"]


def test_brand_config_is_empty_not_explosive_when_nothing_is_readable(profile, no_pyyaml):
    """No sidecar and no PyYAML — callers all have defaults, so this must not raise."""
    assert brand.config(profile) == {}


def test_max_retries_falls_back_to_the_default_without_config(profile, no_pyyaml):
    assert onboarding.max_retries() == onboarding.DEFAULT_MAX_RETRIES


def test_answer_completes_a_full_turn_without_pyyaml(profile, no_pyyaml, monkeypatch):
    """The exact call that crashed: a rejected answer, which takes the retry path — the
    one path that reads brand config. The 2026-07-22 original was the hyphenated handle
    "mike-231"; the gate accepts those now, so the junk here is a genuine non-answer."""
    brand.write_sidecar(profile, {"onboarding": {"max_retries": 3}})
    conn = store.connect(str(profile / "ace" / "ace.db"))
    onboarding.start(conn, "@john", now=100.0)

    out = onboarding.answer(conn, "@john", "its on my other phone rn", now=200.0)

    assert out["ok"] is False and out["reason"] == "not_a_handle"
    assert out["retries"] == 1                 # ONE strike for one message, not two
    assert out["ask"] == "tiktok"
    conn.close()


def test_slack_channel_resolves_without_pyyaml(profile, no_pyyaml, monkeypatch):
    brand.write_sidecar(profile, {"slack_channel": "#ace-escalations"})
    assert slack_cli.load_ace_config(profile)["slack_channel"] == "#ace-escalations"


def test_role_assignment_reads_the_guild_id_without_pyyaml(profile, no_pyyaml, monkeypatch):
    """Roles are the creator's key to the server — this path failing is the worst case."""
    brand.write_sidecar(profile, {"discord": {"guild_id": "1234"},
                                  "onboarding": {"creator_roles": ["onboarded"]}})
    monkeypatch.setattr(assign_role, "bot_token", lambda p: "tok")
    seen = {}

    def fake_request(token, path, method="GET"):
        seen.setdefault("paths", []).append(path)
        return [{"id": "r1", "name": "onboarded"}] if path.endswith("/roles") else {}

    monkeypatch.setattr(assign_role, "request", fake_request)
    out = assign_role.assign("42", profile=profile)

    assert out["ok"] is True and out["assigned"] == ["onboarded"]
    assert "/guilds/1234/roles" in seen["paths"]


def test_missing_brand_config_is_a_clear_message_not_a_traceback(profile, no_pyyaml, monkeypatch):
    monkeypatch.setattr(assign_role, "bot_token", lambda p: "tok")
    out = assign_role.assign("42", profile=profile)
    assert out["ok"] is False and "setup-brand" in out["error"]
