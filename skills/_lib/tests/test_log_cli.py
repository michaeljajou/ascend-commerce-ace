"""_lib/log_cli.py: support logging respects the effective feature policy."""

import json

import pytest

from _lib import log_cli, store


def test_disabled_general_qa_refuses_before_opening_store(tmp_path, monkeypatch, capsys):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(
        json.dumps({"features": {"general_qa": False}}), encoding="utf-8"
    )
    monkeypatch.setattr(store, "connect",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("store read")))
    monkeypatch.setenv("ACE_DATA_DIR", str(ace_dir))

    assert log_cli.main(["interaction", "--status", "answered"]) == 0
    assert json.loads(capsys.readouterr().out) == {"disabled": "general_qa"}


def test_cli_rejects_a_cross_profile_policy_override(tmp_path):
    with pytest.raises(SystemExit):
        log_cli.main([
            "--profile-dir", str(tmp_path), "interaction", "--status", "answered",
        ])
