"""A brand spec with no feature settings must get the profile it got before they existed.

**The bug this test exists for.** ENG-299 (29 Sep 2026): no test compared a full-feature
profile with what `main` wrote, so the feature work reworded the digest job's prompt for
every existing brand without a test failing. The files under
tests/fixtures/legacy-brand/main were written by `main`; see the README beside them.

**The second bug.** ENG-299 agent review round 7 (29 Sep 2026): the first version of this
test ran setup into an empty profile. An existing brand has a knowledge file, and with one
present setup copied its onboarding section into `ace.onboarding.guidance` for every
profile, which `main` never wrote. Each check now also runs with a knowledge file.
"""

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import setup  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "tests" / "fixtures" / "legacy-brand"
SPECS = ("full", "minimal")
KNOWLEDGE = {
    "no-knowledge": None,
    "template-knowledge": REPO / "skills" / "setup-brand" / "templates" / "knowledge.template.yaml",
    "pilot-knowledge": REPO / "tests" / "fixtures" / "pilot-brand" / "knowledge.yaml",
}
PROFILES = [(spec, knowledge) for spec in SPECS for knowledge in KNOWLEDGE]
PROFILE_IDS = [f"{spec}-{knowledge}" for spec, knowledge in PROFILES]

ALL_ENABLED = {name: True for name in setup.FEATURE_NAMES}
POLICY_BLOCK = (
    "## Effective feature policy\n"
    "- general_qa: enabled\n"
    "- moderation: enabled\n"
    "- announcements: enabled\n"
    "- engagement: enabled\n"
    "- reporting: enabled\n"
    "\n"
    "General Q&A is enabled. Follow the channel map and grounding rules below.\n"
    "\n"
    "{onboarding}\n"
    "\n"
)
ONBOARDING_LINE = {
    True: "onboarding.enabled is true. Handle onboarding only in its configured private thread.",
    False: "onboarding.enabled is false. The profile is prepared but onboarding must not start.",
}


def load_spec(name: str) -> dict:
    return json.loads((FIXTURE / f"{name}.spec.json").read_text(encoding="utf-8"))


def from_main(name: str, filename: str) -> str:
    return (FIXTURE / "main" / name / filename).read_text(encoding="utf-8")


@pytest.fixture
def written(request, tmp_path, monkeypatch):
    """The profile today's setup writes for the spec, with machine paths replaced."""
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("ACE_DEFAULT_SLACK_CHANNEL", raising=False)
    profile = tmp_path / "profile"
    name, knowledge = request.param
    spec = load_spec(name)
    assert "features" not in spec
    if KNOWLEDGE[knowledge]:
        (profile / "ace").mkdir(parents=True)
        (profile / "ace" / "knowledge.yaml").write_text(
            KNOWLEDGE[knowledge].read_text(encoding="utf-8"), encoding="utf-8")
    paths = setup.write_profile(spec, profile)

    def read(key: str) -> str:
        text = Path(paths[key]).read_text(encoding="utf-8")
        return text.replace(str(profile), "<PROFILE>").replace(str(REPO), "<REPO>")

    return name, spec, read


@pytest.mark.parametrize("written", PROFILES, ids=PROFILE_IDS, indirect=True)
def test_unchanged_spec_gets_the_soul_main_wrote_plus_the_policy_block(written):
    name, spec, read = written
    onboarding_enabled = bool((spec.get("onboarding") or {}).get("enabled", False))
    block = POLICY_BLOCK.format(onboarding=ONBOARDING_LINE[onboarding_enabled])
    soul = read("soul")

    assert soul.count(block) == 1
    assert soul.replace(block, "") == from_main(name, "SOUL.md")


@pytest.mark.parametrize("written", PROFILES, ids=PROFILE_IDS, indirect=True)
def test_unchanged_spec_gets_the_cron_jobs_main_wrote(written):
    name, _, read = written
    assert read("cronjobs") == from_main(name, "cronjobs.yaml")


@pytest.mark.parametrize("written", PROFILES, ids=PROFILE_IDS, indirect=True)
def test_unchanged_spec_gets_the_config_main_wrote_plus_enabled_features(written):
    name, _, read = written
    config = yaml.safe_load(read("config"))
    expected = yaml.safe_load(from_main(name, "config.yaml"))

    assert config["ace"].pop("features") == ALL_ENABLED
    assert config == expected
    assert list(config) == list(expected)               # Hermes key order kept


@pytest.mark.parametrize("written", PROFILES, ids=PROFILE_IDS, indirect=True)
def test_unchanged_spec_gets_the_sidecar_main_wrote_plus_enabled_features(written):
    name, _, read = written
    sidecar = json.loads(read("brand_json"))

    assert sidecar.pop("features") == ALL_ENABLED
    assert sidecar == json.loads(from_main(name, "brand.json"))


def test_the_template_knowledge_file_has_the_section_setup_used_to_copy():
    """Keeps the template cases above meaningful: they need a complete onboarding section."""
    text = KNOWLEDGE["template-knowledge"].read_text(encoding="utf-8")
    section = yaml.safe_load(text)["onboarding"]
    assert all(section.get(key) for key in ("channels", "getting_started", "how_to_reach_team"))


def test_unchanged_spec_does_not_depend_on_a_readable_knowledge_file(tmp_path, monkeypatch):
    """`main` never opened the knowledge file during setup, so a brand whose file has a
    YAML error could still re-run setup. Reading it for every profile broke that."""
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("ACE_DEFAULT_SLACK_CHANNEL", raising=False)
    profile = tmp_path / "profile"
    (profile / "ace").mkdir(parents=True)
    (profile / "ace" / "knowledge.yaml").write_text("onboarding: [unclosed\n", encoding="utf-8")

    paths = setup.write_profile(load_spec("full"), profile)

    sidecar = json.loads(Path(paths["brand_json"]).read_text(encoding="utf-8"))
    assert "guidance" not in sidecar["onboarding"]
