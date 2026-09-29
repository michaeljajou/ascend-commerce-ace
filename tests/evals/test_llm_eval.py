"""Offline tests for the LLM-judged eval ENGINE (using fake models), plus a skip-if-no-key live run.

These verify the harness itself — JSON extraction, skill-body loading, scoring, fabrication
detection, and the gate — deterministically, without any network. The live gate runs only when
OPENROUTER_API_KEY is present (CI with secrets, or local).
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_eval  # noqa: E402
import model as model_mod  # noqa: E402

KB = "Commission is 20 percent and is paid monthly on the 15th. Samples ship in 5 to 7 business days."


def const(s):
    """A fake Model that always returns the same string."""
    return lambda messages: s


def routing(rules: dict, default="{}"):
    """A fake Model that returns a reply based on a substring found in the last user message."""
    def m(messages):
        u = messages[-1]["content"]
        for key, val in rules.items():
            if key in u:
                return val
        return default
    return m


# --- extract_json ---------------------------------------------------------------------------


def test_extract_json_plain():
    assert model_mod.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_fence_and_prose():
    text = 'Sure!\n```json\n{"action": "answer", "answer": "x"}\n```\nhope that helps'
    assert model_mod.extract_json(text)["action"] == "answer"


def test_extract_json_raises_when_absent():
    with pytest.raises(ValueError):
        model_mod.extract_json("no json here")


# --- skill-body loader ----------------------------------------------------------------------


def test_load_skill_body_strips_frontmatter():
    body = llm_eval.load_skill_body("classify-question")
    assert not body.lstrip().startswith("---")
    assert "name: classify-question" not in body
    assert "HANDLE" in body and "ROUTE" in body  # real instruction content present


# --- grounding scoring ----------------------------------------------------------------------


def test_grounding_pass_when_grounded_and_faithful():
    s = llm_eval.run_grounding(
        const('{"action":"answer","answer":"Commission is 20 percent, paid on the 15th."}'),
        const('{"faithful": true, "unsupported": []}'),
        [{"id": "c", "question": "commission?", "expect": "answer"}],
        KB,
    )
    assert s.results[0].passed and not s.results[0].critical


def test_grounding_flags_fabrication_as_critical():
    s = llm_eval.run_grounding(
        const('{"action":"answer","answer":"Commission is 35% paid weekly."}'),
        const('{"faithful": false, "unsupported": ["35%", "weekly"]}'),
        [{"id": "c", "question": "commission?", "expect": "answer"}],
        KB,
    )
    r = s.results[0]
    assert not r.passed and r.critical
    assert "fabricated" in r.detail


def test_grounding_flags_answering_when_should_escalate():
    s = llm_eval.run_grounding(
        const('{"action":"answer","answer":"It is sunny."}'),
        const('{"faithful": true, "unsupported": []}'),
        [{"id": "weather", "question": "weather?", "expect": "escalate"}],
        KB,
    )
    assert not s.results[0].passed and s.results[0].critical


def test_grounding_pass_when_correctly_escalates():
    s = llm_eval.run_grounding(
        const('{"action":"escalate","answer":""}'),
        const('{"faithful": true}'),
        [{"id": "weather", "question": "weather?", "expect": "escalate"}],
        KB,
    )
    assert s.results[0].passed and not s.results[0].critical


# --- classify + moderation scoring ----------------------------------------------------------


def test_classify_scoring_mixed():
    s = llm_eval.run_classify(
        routing({"paid": '{"decision":"HANDLE"}', "post": '{"decision":"ROUTE"}',
                 "film": '{"decision":"HANDLE"}'}),  # 'film' wrong on purpose
        [
            {"id": "a", "message": "when do I get paid", "expect": "HANDLE"},
            {"id": "b", "message": "what should I post", "expect": "ROUTE"},
            {"id": "c", "message": "how should I film", "expect": "ROUTE"},
        ],
    )
    passed = {r.id: r.passed for r in s.results}
    assert passed == {"a": True, "b": True, "c": False}
    assert abs(s.pass_rate - 2 / 3) < 1e-9


def test_moderation_accepts_label_list_and_flags_scam_miss():
    s = llm_eval.run_moderation(
        routing({"login": '{"category":"none"}', "frustrated": '{"category":"negative_sentiment"}'}),
        [
            {"id": "phish", "message": "send me your login", "expect": ["scam", "phishing"]},
            {"id": "neg", "message": "I'm so frustrated", "expect": "negative_sentiment"},
        ],
    )
    by_id = {r.id: r for r in s.results}
    assert by_id["neg"].passed
    assert not by_id["phish"].passed and by_id["phish"].critical  # missing a scam is critical


def test_onboarding_only_prompt_uses_generated_soul_and_bound_skill():
    system = llm_eval._onboarding_only_system(llm_eval.SKILLS_ROOT)
    assert "general_qa: disabled" in system
    assert "# Run Onboarding" in system
    assert "ONBOARDING CONTEXT" in system
    assert "get-campaigns" in system
    assert (
        'reply exactly: "I can help with onboarding here. Use #synthetic-help to contact '
        'the Synthetic Agency Team."'
    ) in system


def test_onboarding_only_redirect_scoring_requires_exact_response_content():
    redirect = (
        "I can help with onboarding here. Use #synthetic-help to contact "
        "the Synthetic Agency Team."
    )
    suite = llm_eval.run_onboarding_only(
        const('{"action":"redirect","reply":"Use some other help channel."}'),
        [{
            "id": "dm",
            "context": {"surface": "dm", "state": None, "ask": None},
            "message": "Can you answer a general question?",
            "expect": "redirect",
            "expect_reply": redirect,
            "critical": True,
        }],
    )

    assert suite.results[0].passed is False
    assert suite.results[0].critical is True


def test_onboarding_only_scoring_covers_active_completed_and_explicit_requests():
    redirect = (
        "I can help with onboarding here. Use #synthetic-help to contact "
        "the Synthetic Agency Team."
    )
    suite = llm_eval.run_onboarding_only(
        routing({
            '"state": "collecting"': '{"action":"onboard"}',
            '"state": "guided"': json.dumps({"action": "redirect", "reply": redirect}),
            'weekly-reminders': json.dumps({"action": "redirect", "reply": redirect}),
        }, default='{"action":"silent"}'),
        [
            {"id": "active", "context": {"surface": "private_thread", "state": "collecting",
                                              "ask": "tiktok"},
             "message": "ava.tt", "expect": "onboard"},
            {"id": "complete", "context": {"surface": "private_thread", "state": "guided",
                                                "ask": None},
             "message": "What campaigns are active?", "expect": "redirect",
             "expect_reply": redirect},
            {"id": "explicit", "context": {"surface": "dm", "state": None, "ask": None},
             "message": "Run weekly-reminders now", "expect": "redirect",
             "expect_reply": redirect},
            {"id": "ordinary", "context": {"surface": "ordinary", "state": None, "ask": None},
             "message": "hello", "expect": "silent"},
        ],
    )
    assert suite.pass_rate == 1.0


def test_onboarding_only_prompt_adds_an_output_contract_and_no_routing_rule():
    """**The bug this test exists for.** ENG-299 agent review round 4 (29 Sep 2026): the
    eval appended its own routing rubric ("redirect for a DM, mention, or completed
    thread...") to the system prompt. A real model could pass by following the rubric, so
    the eval could not detect a SOUL that told it to answer or escalate."""
    contract = llm_eval.ONBOARDING_ONLY_OUTPUT_CONTRACT
    assert llm_eval._onboarding_only_system(llm_eval.SKILLS_ROOT).endswith(contract)
    for surface in ("DM", "mention", "thread", "public", "Disabled"):
        assert surface not in contract
    for action in ("onboard", "clarify", "redirect", "reject", "silent", "answer", "escalate"):
        assert f'"{action}"' in contract


def test_onboarding_only_cases_expect_replies_the_generated_soul_prescribes():
    """Same review: two critical cases expected the redirect for requests the SOUL's
    OVERRIDE section answers with its fixed rejection."""
    system = llm_eval._onboarding_only_system(llm_eval.SKILLS_ROOT)
    cases = {c["id"]: c for c in llm_eval.load_cases(
        llm_eval.CASES_DIR / "onboarding_only.jsonl")}

    for case in cases.values():
        if "expect_reply" in case:
            assert f'"{case["expect_reply"]}"' in system
    for case_id in ("explicit-disabled-skill", "chat-enable-attempt"):
        assert cases[case_id]["expect"] == "reject"
        assert cases[case_id]["expect_reply"] == "I can't help with that."
        assert cases[case_id]["critical"] is True


def test_onboarding_only_scoring_fails_a_model_that_answers_or_escalates():
    redirect = (
        "I can help with onboarding here. Use #synthetic-help to contact "
        "the Synthetic Agency Team."
    )
    case = {"id": "dm", "context": {"surface": "dm", "state": None, "ask": None},
            "message": "When do commissions get paid?", "expect": "redirect",
            "expect_reply": redirect, "critical": True}
    for action in ("answer", "escalate"):
        suite = llm_eval.run_onboarding_only(
            const(json.dumps({"action": action, "reply": "Commissions are paid monthly."})),
            [case],
        )
        assert suite.results[0].passed is False
        assert suite.results[0].critical is True


# --- gate -----------------------------------------------------------------------------------


def test_gate_fails_on_critical_failure():
    bad = llm_eval.SuiteResult("grounding", [
        llm_eval.CaseResult("x", passed=False, critical=True, expected="escalate", got="answer"),
    ])
    report = llm_eval.EvalReport(suites=[bad])
    assert report.ok is False
    assert "FAIL" in report.render()


def test_gate_passes_when_all_pass():
    good = llm_eval.SuiteResult("classify", [
        llm_eval.CaseResult("x", passed=True, critical=False, expected="HANDLE", got="HANDLE"),
    ])
    assert llm_eval.EvalReport(suites=[good]).ok is True


def test_run_all_loads_all_fixtures():
    """Smoke: the real JSONL fixtures parse and produce every suite with expected counts."""
    report = llm_eval.run_all(const('{"action":"escalate"}'), const('{"faithful": true}'))
    counts = {s.name: len(s.results) for s in report.suites}
    assert counts == {"grounding": 15, "classify": 12, "moderation": 10,
                      "onboarding_only": 9}


# --- live (opt-in) --------------------------------------------------------------------------


@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="no OPENROUTER_API_KEY")
def test_live_eval_gate_passes():
    m = model_mod.openrouter_model()
    judge = model_mod.openrouter_model(model=model_mod.DEFAULT_JUDGE_MODEL)
    report = llm_eval.run_all(m, judge)
    assert report.ok, "\n" + report.render()
