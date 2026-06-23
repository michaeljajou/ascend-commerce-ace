"""Tests for the bundle installer (install.sh).

We shell out to the real bash script. It registers the repo's skills/ dir in
Hermes' config under skills.external_dirs (live, in-place) rather than copying
skills — so Hermes discovers all skills at once and skills/_lib stays a sibling.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "install.sh"
ACE_CLI = REPO / "bin" / "ace"
SKILLS_DIR = REPO / "skills"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")

# a python that has PyYAML, for the real (non-dry-run) config merge
_VENV_PY = REPO / ".venv" / "bin" / "python"
ACE_PYTHON = str(_VENV_PY) if _VENV_PY.exists() else (shutil.which("python3") or "python3")


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


# ── dry-run dispatch ────────────────────────────────────────────────────────────

def test_defaults_to_hermes():
    r = run(["--dry-run", "--repo", str(REPO)])
    assert r.returncode == 0, out(r)
    assert "external_dirs" in out(r)
    assert str(SKILLS_DIR) in out(r)


def test_explicit_orchestrator_flag():
    r = run(["--orchestrator", "hermes", "--dry-run", "--repo", str(REPO)])
    assert r.returncode == 0, out(r)
    assert "external_dirs" in out(r)


def test_env_var_selects_orchestrator():
    r = run(["--dry-run", "--repo", str(REPO)], extra_env={"ACE_ORCHESTRATOR": "hermes"})
    assert r.returncode == 0, out(r)
    assert "external_dirs" in out(r)


def test_dry_run_changes_nothing(tmp_path):
    cfg = tmp_path / "config.yaml"
    r = run(["--dry-run", "--repo", str(REPO), "--hermes-config", str(cfg)])
    assert r.returncode == 0, out(r)
    assert not cfg.exists()  # dry-run must not write


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


# ── real config registration ────────────────────────────────────────────────────

def test_registers_external_dir_in_fresh_config(tmp_path):
    cfg = tmp_path / "hermes" / "config.yaml"
    r = run(
        ["--no-deps", "--repo", str(REPO), "--hermes-config", str(cfg)],
        extra_env={"ACE_PYTHON": ACE_PYTHON},
    )
    assert r.returncode == 0, out(r)
    assert cfg.exists()
    import yaml  # available in the test env

    data = yaml.safe_load(cfg.read_text())
    assert data["skills"]["external_dirs"] == [str(SKILLS_DIR)]


def test_registration_is_idempotent(tmp_path):
    cfg = tmp_path / "config.yaml"
    args = ["--no-deps", "--repo", str(REPO), "--hermes-config", str(cfg)]
    env = {"ACE_PYTHON": ACE_PYTHON}
    assert run(args, extra_env=env).returncode == 0
    assert run(args, extra_env=env).returncode == 0  # second run
    assert cfg.read_text().count(str(SKILLS_DIR)) == 1  # no duplicate


def test_profile_targets_profile_config(tmp_path):
    # HERMES_HOME=tmp; a profile dir exists → --profile writes to <home>/profiles/<name>/config.yaml
    home = tmp_path
    pdir = home / "profiles" / "acme"
    pdir.mkdir(parents=True)
    r = run(
        ["--profile", "acme", "--repo", str(REPO)],
        extra_env={"HERMES_HOME": str(home), "ACE_PYTHON": ACE_PYTHON},
    )
    assert r.returncode == 0, out(r)
    cfg = pdir / "config.yaml"
    assert cfg.exists()
    import yaml

    assert yaml.safe_load(cfg.read_text())["skills"]["external_dirs"] == [str(SKILLS_DIR)]


def test_profile_missing_errors_without_create(tmp_path):
    r = run(
        ["--profile", "ghost", "--dry-run", "--repo", str(REPO)],
        extra_env={"HERMES_HOME": str(tmp_path)},
    )
    assert r.returncode != 0
    assert "not found" in out(r).lower()


def test_profile_create_dry_run_uses_singular_profile_command(tmp_path):
    r = run(
        ["--profile", "demo", "--create", "--dry-run", "--repo", str(REPO)],
        extra_env={"HERMES_HOME": str(tmp_path)},
    )
    assert r.returncode == 0, out(r)
    assert "hermes profile create demo" in out(r)   # singular, not "profiles"
    assert "external_dirs" in out(r)


def test_global_install_links_ace_cli(tmp_path):
    bindir = tmp_path / "bin"
    cfg = tmp_path / "config.yaml"
    r = run(
        ["--no-deps", "--repo", str(REPO), "--hermes-config", str(cfg)],
        extra_env={"ACE_BIN_DIR": str(bindir), "ACE_PYTHON": ACE_PYTHON, "PATH": str(Path(BASH).parent)},
    )
    assert r.returncode == 0, out(r)
    link = bindir / "ace"
    assert link.is_symlink()
    assert link.resolve() == ACE_CLI.resolve()


# ── ace CLI dispatch ─────────────────────────────────────────────────────────────

def run_ace(args, extra_env=None):
    env = {"HOME": str(REPO), "PATH": str(Path(BASH).parent)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run([BASH, str(ACE_CLI), *args], capture_output=True, text=True, env=env)


def test_ace_help():
    r = run_ace(["help"])
    assert r.returncode == 0
    assert "ace brand create" in out(r)


def test_ace_brand_create_requires_name():
    r = run_ace(["brand", "create"])
    assert r.returncode != 0
    assert "usage: ace brand create" in out(r).lower()


def test_ace_brand_create_dispatches_to_installer(tmp_path):
    r = run_ace(
        ["brand", "create", "demo", "--dry-run"],
        extra_env={"HERMES_HOME": str(tmp_path)},
    )
    assert r.returncode == 0, out(r)
    assert "hermes profile create demo" in out(r)
    assert "external_dirs" in out(r)


def test_ace_unknown_command_errors():
    r = run_ace(["frobnicate"])
    assert r.returncode != 0
    assert "unknown command" in out(r).lower()


def test_preserves_existing_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model: openrouter/anthropic/claude-sonnet-4-6\nskills:\n  external_dirs:\n    - /other/skills\n")
    r = run(
        ["--no-deps", "--repo", str(REPO), "--hermes-config", str(cfg)],
        extra_env={"ACE_PYTHON": ACE_PYTHON},
    )
    assert r.returncode == 0, out(r)
    import yaml

    data = yaml.safe_load(cfg.read_text())
    assert data["model"] == "openrouter/anthropic/claude-sonnet-4-6"  # untouched
    assert "/other/skills" in data["skills"]["external_dirs"]  # preserved
    assert str(SKILLS_DIR) in data["skills"]["external_dirs"]  # added
