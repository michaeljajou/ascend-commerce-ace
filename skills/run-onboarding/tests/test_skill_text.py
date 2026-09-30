"""What the onboarding and nudge skills tell a brand with general Q&A enabled.

**The bug this test exists for.** ENG-299 (29 Sep 2026): the onboarding-only work rewrote
these instructions for every profile. A brand with general Q&A enabled was told to send a
"fixed redirect" to a creator who asked a question during onboarding or after it, where
`main` told it to answer. Its SOUL carries no redirect text, so the reply had no source.
The skill files are shared by every profile, so each restriction must name its condition.
"""

import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[2]


def flat(text: str) -> str:
    return " ".join(text.split())


def skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def passages(text: str) -> list[str]:
    """Paragraphs, list items, and table rows, each as one line."""
    blocks = re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)|\n(?=\|)", text)
    return [flat(block) for block in blocks if block.strip()]


MAIN_RUN_ONBOARDING = (
    'The one exception: if their message is plainly a QUESTION rather than an answer ("what '
    'is this?", "who are you?"), just answer it and re-ask the outstanding question — don\'t '
    "run `answer` on a question.",
    "1. What the key channels are for — clickable `<#id>` tags from the SOUL Channel "
    "directory, just the three or four that matter to someone brand new.",
    "2. How to request samples / join campaigns — ground in `get-knowledge` (samples section).",
    "3. **What's actually running right now** — ground in `get-campaigns`, never boilerplate.",
    "4. How to get help: ask Ace in the community channel, the team for anything creative.",
    "5. A nudge to introduce themselves.",
    "Never re-run the flow for someone already `guided`/`active` — answer whatever they asked "
    "instead. A duplicate join resumes, never restarts.",
    "Guidance references the actual live campaign and clickable channel tags.",
)


@pytest.mark.parametrize("instruction", MAIN_RUN_ONBOARDING)
def test_run_onboarding_keeps_the_instructions_main_gave_a_general_qa_brand(instruction):
    assert instruction in flat(skill("run-onboarding"))


def test_every_redirect_instruction_names_disabled_general_qa():
    found = [p for p in passages(skill("run-onboarding")) if "redirect" in p.lower()]

    assert found
    for passage in found:
        assert "`general_qa` is disabled" in passage, passage


@pytest.mark.parametrize("instruction", [
    "a clarification about the current field",
    "the clarification does not consume a retry",
    "Do not call `get-knowledge` or `get-campaigns`.",
    "Give the configured human-help destination.",
])
def test_run_onboarding_keeps_the_restricted_instructions(instruction):
    assert instruction in flat(skill("run-onboarding"))


def test_nudge_inactive_grounds_nudges_the_way_main_did():
    text = flat(skill("nudge-inactive"))

    assert "(introduce themselves, join the current campaign). Ground specifics with " \
           "`get-knowledge`." in text
    assert "do not read the general knowledge file" not in text
