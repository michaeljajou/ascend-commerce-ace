"""_lib/brand.py: brand configuration and feature policy."""

import json
import builtins

import pytest

from _lib import brand


def test_post_channel_is_the_first_post_behaviour_channel_by_name():
    cfg = {"discord": {"channels": {"community-chat": "FULL_ACTIVE", "challenges": "POST_ANSWER",
                                    "announcements": "POST_ONLY", "campaigns": "POST_ANSWER"}}}
    assert brand.post_channel(cfg) == "announcements"


def test_post_channel_is_none_without_a_post_behaviour_channel():
    assert brand.post_channel({"discord": {"channels": {"community-chat": "FULL_ACTIVE"}}}) is None
    assert brand.post_channel({}) is None


def test_legacy_config_enables_every_feature():
    assert brand.resolve_features({}) == {name: True for name in brand.FEATURE_NAMES}


def test_explicit_feature_values_override_legacy_defaults():
    features = brand.resolve_features({"features": {"general_qa": False, "reporting": False}})
    assert features["general_qa"] is False
    assert features["reporting"] is False
    assert features["moderation"] is True


@pytest.mark.parametrize("features", [
    {"unknown": False},
    {"general_qa": 0},
    {"moderation": "false"},
    [],
])
def test_invalid_explicit_feature_policy_is_rejected(features):
    with pytest.raises(brand.PolicyError):
        brand.resolve_features({"features": features})


def test_policy_loader_distinguishes_legacy_absence_from_malformed_sidecar(tmp_path):
    assert brand.load_policy(tmp_path) == {name: True for name in brand.FEATURE_NAMES}

    path = brand.sidecar_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(brand.PolicyError, match="brand.json"):
        brand.load_policy(tmp_path)

    path.write_text(json.dumps({"features": {"general_qa": False}}), encoding="utf-8")
    assert brand.load_policy(tmp_path)["general_qa"] is False


def test_missing_sidecar_fails_closed_when_yaml_declares_features_without_pyyaml(
        tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(
        "ace:\n  features:\n    general_qa: false\n", encoding="utf-8"
    )
    real_import = builtins.__import__

    def no_yaml(name, *args, **kwargs):
        if name == "yaml" or name.startswith("yaml."):
            raise ImportError("No module named yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_yaml)
    with pytest.raises(brand.PolicyError, match="brand.json"):
        brand.load_policy(tmp_path)


def test_missing_sidecar_keeps_legacy_defaults_without_explicit_features(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("ace:\n  brand_id: legacy\n", encoding="utf-8")
    real_import = builtins.__import__

    def no_yaml(name, *args, **kwargs):
        if name == "yaml" or name.startswith("yaml."):
            raise ImportError("No module named yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_yaml)
    assert brand.load_policy(tmp_path) == brand.DEFAULT_FEATURES


def test_missing_sidecar_detects_compact_ace_feature_policy_without_pyyaml(
        tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(
        "ace: {features: {general_qa: false}}\n", encoding="utf-8"
    )
    real_import = builtins.__import__

    def no_yaml(name, *args, **kwargs):
        if name == "yaml" or name.startswith("yaml."):
            raise ImportError("No module named yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_yaml)
    with pytest.raises(brand.PolicyError, match="brand.json"):
        brand.load_policy(tmp_path)


def test_unrelated_nested_features_do_not_mark_legacy_ace_policy(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(
        "ace:\n  brand_id: legacy\nother:\n  features:\n    beta: true\n", encoding="utf-8"
    )
    real_import = builtins.__import__

    def no_yaml(name, *args, **kwargs):
        if name == "yaml" or name.startswith("yaml."):
            raise ImportError("No module named yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_yaml)
    assert brand.load_policy(tmp_path) == brand.DEFAULT_FEATURES
