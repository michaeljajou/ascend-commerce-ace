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
from pathlib import Path

SIDECAR = "brand.json"


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
