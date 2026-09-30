"""The brand's ``ace:`` config, readable without PyYAML.

Every script in this bundle needs some of it — the guild id to assign roles, the creator
role names, which Slack channel to post to, the retry budget. It lives in the Hermes
profile's ``config.yaml``, which needs PyYAML to read.

**The agent's code sandbox has no third-party packages, PyYAML included.** Diagnosed in QA
when a single creator message cost six tool calls and 112 seconds: `onboarding.py answer`
died on `import yaml`, and the agent went off trying to `uv pip install`, then
`apt-get install`, then building itself a venv — before finally re-running the script and
answering the creator. Worse, the crash landed *after* the retry counter had incremented,
so the creator was charged two strikes for one message.

So ``setup-brand`` also writes a plain-JSON sidecar next to the store, and this loader
prefers it. stdlib only, no install step, no sandbox surprises. YAML remains the source of
truth and the fallback for a profile written before this existed.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SIDECAR = "brand.json"

FEATURE_NAMES = (
    "general_qa",
    "moderation",
    "announcements",
    "engagement",
    "reporting",
)
DEFAULT_FEATURES = {name: True for name in FEATURE_NAMES}
DEFAULT_ONBOARDING_REDIRECT = (
    "I can help with onboarding here. For anything else, please use the team-help option "
    "in your onboarding guidance."
)


class PolicyError(ValueError):
    """The profile contains an explicit feature policy that cannot be trusted."""


def resolve_features(ace_config: dict) -> dict[str, bool]:
    """Return the effective feature map. Missing legacy settings remain enabled."""
    if not isinstance(ace_config, dict):
        raise PolicyError("ace config must be an object")
    if "features" not in ace_config:
        return dict(DEFAULT_FEATURES)
    explicit = ace_config["features"]
    if not isinstance(explicit, dict):
        raise PolicyError("ace.features must be an object")
    unknown = sorted(set(explicit) - set(FEATURE_NAMES))
    if unknown:
        raise PolicyError(f"unknown ace.features names: {unknown}")
    invalid = sorted(name for name, value in explicit.items() if type(value) is not bool)
    if invalid:
        raise PolicyError(f"ace.features values must be booleans: {invalid}")
    return {**DEFAULT_FEATURES, **explicit}


def profile_dir() -> Path:
    """The Hermes profile root (ACE_DATA_DIR is ``<profile>/ace`` by contract)."""
    if data_dir := os.environ.get("ACE_DATA_DIR"):
        return Path(data_dir).parent
    return Path(os.environ.get("HERMES_HOME", "."))


def sidecar_path(profile: Path | None = None) -> Path:
    return (profile or profile_dir()) / "ace" / SIDECAR


def config(profile: Path | None = None) -> dict:
    """The ``ace:`` block. Returns ``{}`` rather than raising — every caller has a sane
    default, and a missing config must never take a creator's onboarding down with it."""
    profile = profile or profile_dir()
    try:
        return json.loads(sidecar_path(profile).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        pass
    return _from_yaml(profile)


def load_policy(profile: Path | None = None) -> dict[str, bool]:
    """Load policy without treating malformed explicit settings as legacy defaults.

    A missing sidecar is allowed for profiles created before feature settings existed.
    A present but unreadable sidecar is a configuration error and fails closed.
    """
    profile = profile or profile_dir()
    path = sidecar_path(profile)
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PolicyError(f"cannot read {SIDECAR}: {exc}") from exc
        return resolve_features(value)

    cfg_path = profile / "config.yaml"
    if not cfg_path.exists():
        return dict(DEFAULT_FEATURES)
    config_text = cfg_path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        # Existing sandbox profiles without a sidecar predate feature policy only when
        # config.yaml also has no explicit policy. A missing deployment artifact must not
        # turn a restricted profile back on.
        if _config_declares_ace_features(config_text):
            raise PolicyError(
                "config.yaml declares ace.features but brand.json is missing and PyYAML "
                "is unavailable"
            )
        return dict(DEFAULT_FEATURES)
    try:
        root = yaml.safe_load(config_text) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise PolicyError(f"cannot read config.yaml feature policy: {exc}") from exc
    if not isinstance(root, dict):
        raise PolicyError("config.yaml root must be an object")
    ace = root.get("ace") or {}
    return resolve_features(ace)


def feature_enabled(name: str, profile: Path | None = None) -> bool:
    if name not in FEATURE_NAMES:
        raise PolicyError(f"unknown feature name: {name}")
    return load_policy(profile)[name]


def onboarding_redirect(ace_config: dict) -> str:
    """Return the exact restricted reply compiled from bounded profile guidance."""
    if not isinstance(ace_config, dict):
        return DEFAULT_ONBOARDING_REDIRECT
    onboarding = ace_config.get("onboarding") or {}
    guidance = onboarding.get("guidance") or {}
    how_to_reach_team = guidance.get("how_to_reach_team") if isinstance(guidance, dict) else None
    if not isinstance(how_to_reach_team, str) or not how_to_reach_team.strip():
        return DEFAULT_ONBOARDING_REDIRECT
    return "I can help with onboarding here. " + how_to_reach_team.strip()


def _config_declares_ace_features(text: str) -> bool:
    """Detect a direct ``ace.features`` key without parsing YAML."""
    lines = text.splitlines()
    ace_line = None
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw == raw.lstrip() and re.match(r"^ace\s*:", stripped):
            if re.search(r"^ace\s*:\s*\{.*\bfeatures\s*:", stripped):
                return True
            ace_line = index
            break
    if ace_line is None:
        return False

    child_indent = None
    for raw in lines[ace_line + 1:]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:
            break
        if child_indent is None:
            child_indent = indent
        if indent == child_indent and re.match(r"^features\s*:", stripped):
            return True
    return False


def _from_yaml(profile: Path) -> dict:
    cfg_path = profile / "config.yaml"
    try:
        import yaml
    except ImportError:      # the sandbox case this module exists for
        return {}
    try:
        return (yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}).get("ace") or {}
    except (OSError, ValueError):
        return {}


def write_sidecar(profile: Path, ace_config: dict) -> str:
    """Called by setup-brand after it writes config.yaml, so the two never drift."""
    path = sidecar_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ace_config, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


# Channels the brand posts announcements into (and, for POST_ANSWER, also answers in).
POST_BEHAVIORS = frozenset({"POST_ONLY", "POST_ANSWER"})


def post_channel(ace_config: dict) -> str | None:
    """Where automated announcements go: the first POST_ONLY/POST_ANSWER channel by name
    (the rule setup-brand's cron blueprint uses), or None when the brand has no such channel.
    Scripts resolve the name to an id through channel_directory.json at run time."""
    channels = (ace_config.get("discord") or {}).get("channels") or {}
    posting = sorted(name for name, behavior in channels.items() if behavior in POST_BEHAVIORS)
    return posting[0] if posting else None
