"""Tests for the bundle installer (install.sh).

We shell out to the real bash script. It's builtin-only before any orchestrator/
deps command, so we can run it under a hermetic PATH to exercise dispatch without
touching the machine's real tooling.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "install.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def run(args, path=None, extra_env=None):
    """Run the installer. `path` (if given) fully replaces PATH for isolation."""
    env = {"HOME": str(REPO)}  # minimal, deterministic env (no inherited ACE_ORCHESTRATOR)
    if path is not None:
        env["PATH"] = path
    if extra_env:
        env.update(extra_env)
    return subprocess.run([BASH, str(SCRIPT), *args], capture_output=True, text=True, env=env)


def out(r):
    return r.stdout + r.stderr


def test_defaults_to_hermes():
    r = run(["--dry-run", "--repo", str(REPO)])
    assert r.returncode == 0, out(r)
    assert "hermes skills install" in out(r)
    assert str(REPO) in out(r)


def test_explicit_orchestrator_flag():
    r = run(["--orchestrator", "hermes", "--dry-run", "--repo", str(REPO)])
    assert r.returncode == 0, out(r)
    assert "hermes skills install" in out(r)


def test_env_var_selects_orchestrator():
    r = run(["--dry-run", "--repo", str(REPO)], extra_env={"ACE_ORCHESTRATOR": "hermes"})
    assert r.returncode == 0, out(r)
    assert "hermes skills install" in out(r)


def test_dry_run_does_not_require_hermes_cli():
    # empty PATH → no hermes binary, but --dry-run must still succeed (warn, not die)
    r = run(["--dry-run", "--repo", str(REPO)], path="")
    assert r.returncode == 0, out(r)
    assert "hermes skills install" in out(r)


def test_unsupported_orchestrator_errors():
    r = run(["--orchestrator", "nonsense", "--dry-run", "--repo", str(REPO)])
    assert r.returncode != 0
    assert "unsupported orchestrator" in out(r).lower()


def test_bad_repo_path_errors(tmp_path):
    r = run(["--dry-run", "--repo", str(tmp_path)])
    assert r.returncode != 0
    assert "no skills/" in out(r).lower()


def test_help_lists_supported_orchestrators():
    r = run(["--help"])
    assert r.returncode == 0
    assert "hermes" in out(r)
