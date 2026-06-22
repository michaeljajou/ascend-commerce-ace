"""LLM-judged eval engine for the Ace skill bundle.

Runs golden cases through a chat model using the **real `SKILL.md` instruction bodies**, so the
evals test the prompts that actually ship. Three suites:

  - grounding   : answer-from-kb + classify → must answer only when grounded, else escalate.
                  An LLM judge checks faithfulness (catches fabrication, not just wrong action).
  - classify    : classify-question → HANDLE (shop-operator) vs ROUTE (creative-strategist).
  - moderation  : detect-sentiment → category (negative_sentiment/policy_violation/scam/off_topic/none).

Gate: a run fails if ANY critical case fails (answering when it should escalate, or a fabrication),
or if any suite's pass-rate falls below `min_pass_rate`.

Models are injected (`Model = list[messages] -> str`), so the engine is unit-tested offline with
fakes and run live via `run.py` against OpenRouter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from model import Model, extract_json  # tests/evals is added to sys.path by callers

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "skills"
CASES_DIR = Path(__file__).resolve().parent / "cases"
DEFAULT_KNOWLEDGE = REPO_ROOT / "tests" / "fixtures" / "pilot-brand" / "knowledge"

MIN_PASS_RATE = 0.9


# --- loading ---------------------------------------------------------------------------------


def load_skill_body(name: str, skills_root: Path = SKILLS_ROOT) -> str:
    """Return a skill's instruction body (SKILL.md minus the YAML frontmatter)."""
    text = (skills_root / name / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[text.find("\n", end + 1) + 1 :]
    return text.strip()


def load_kb(knowledge_dir: Path = DEFAULT_KNOWLEDGE) -> str:
    return "\n\n".join(
        p.read_text(encoding="utf-8") for p in sorted(knowledge_dir.rglob("*.md"))
    ).strip()


def load_cases(path: Path) -> list[dict]:
    """Load JSONL cases (blank lines and #-comments ignored)."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(json.loads(s))
    return out


# --- results ---------------------------------------------------------------------------------


@dataclass
class CaseResult:
    id: str
    passed: bool
    critical: bool
    expected: str
    got: str
    detail: str = ""


@dataclass
class SuiteResult:
    name: str
    results: list[CaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return sum(r.passed for r in self.results) / len(self.results) if self.results else 1.0

    @property
    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]

    @property
    def critical_failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed and r.critical]


@dataclass
class EvalReport:
    suites: list[SuiteResult] = field(default_factory=list)
    min_pass_rate: float = MIN_PASS_RATE

    @property
    def critical_failures(self) -> list[CaseResult]:
        return [r for s in self.suites for r in s.critical_failures]

    @property
    def ok(self) -> bool:
        if self.critical_failures:
            return False
        return all(s.pass_rate >= self.min_pass_rate for s in self.suites)

    def render(self) -> str:
        lines = [f"Eval report  (gate: no critical failures, each suite ≥ {self.min_pass_rate:.0%})"]
        for s in self.suites:
            mark = "✓" if (s.pass_rate >= self.min_pass_rate and not s.critical_failures) else "✗"
            lines.append(f"  {mark} {s.name:11s} {int(s.pass_rate*100):3d}%  ({len(s.results)-len(s.failures)}/{len(s.results)})")
            for f in s.failures:
                tag = "CRITICAL" if f.critical else "miss"
                lines.append(f"      - [{tag}] {f.id}: expected {f.expected!r} got {f.got!r} — {f.detail}")
        lines.append(f"\nGATE: {'PASS' if self.ok else 'FAIL'}")
        return "\n".join(lines)


# --- prompts ---------------------------------------------------------------------------------


def _grounding_system(skills_root: Path) -> str:
    return (
        load_skill_body("classify-question", skills_root)
        + "\n\n---\n\n"
        + load_skill_body("answer-from-kb", skills_root)
        + "\n\n---\n\n"
        "You are answering one creator message. The only knowledge you may use is the BRAND "
        "KNOWLEDGE provided in the user message. If the answer is not fully supported there, or the "
        "message is creative-strategist scope, you must escalate — never use outside knowledge.\n"
        'Respond ONLY with JSON: {"action": "answer" | "escalate", "answer": "<grounded answer, or empty>"}'
    )


def _classify_system(skills_root: Path) -> str:
    return (
        load_skill_body("classify-question", skills_root)
        + "\n\n---\n\n"
        'Classify the one creator message. Respond ONLY with JSON: {"decision": "HANDLE" | "ROUTE"}'
    )


def _moderation_system(skills_root: Path) -> str:
    return (
        load_skill_body("detect-sentiment", skills_root)
        + "\n\n---\n\n"
        'Classify the one message into a moderation category. Respond ONLY with JSON: '
        '{"category": "negative_sentiment" | "policy_violation" | "scam" | "off_topic" | "none"}'
    )


_JUDGE_SYSTEM = (
    "You are a strict grounding judge. Given BRAND KNOWLEDGE and an ANSWER to a question, decide "
    "whether EVERY factual claim in the answer is directly supported by the knowledge. Unsupported "
    "specifics (numbers, dates, policies, channels) make it unfaithful.\n"
    'Respond ONLY with JSON: {"faithful": true | false, "unsupported": ["..."]}'
)


# --- suites ----------------------------------------------------------------------------------


def judge_faithful(judge: Model, kb: str, question: str, answer: str) -> dict:
    out = extract_json(
        judge(
            [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": f"BRAND KNOWLEDGE:\n{kb}\n\nQUESTION: {question}\n\nANSWER: {answer}"},
            ]
        )
    )
    return {"faithful": bool(out.get("faithful")), "unsupported": out.get("unsupported", [])}


def run_grounding(model: Model, judge: Model, cases: list[dict], kb: str, skills_root: Path = SKILLS_ROOT) -> SuiteResult:
    system = _grounding_system(skills_root)
    suite = SuiteResult("grounding")
    for c in cases:
        expected = c["expect"]  # "answer" | "escalate"
        try:
            out = extract_json(model([
                {"role": "system", "content": system},
                {"role": "user", "content": f"BRAND KNOWLEDGE:\n{kb}\n\nCREATOR MESSAGE:\n{c['question']}"},
            ]))
        except ValueError as e:
            suite.results.append(CaseResult(c["id"], False, True, expected, "parse_error", str(e)))
            continue
        action = out.get("action", "")
        answered = action == "answer"
        action_ok = answered if expected == "answer" else (not answered)

        faithful, detail = True, ""
        if answered:
            j = judge_faithful(judge, kb, c["question"], out.get("answer", ""))
            faithful = j["faithful"]
            if not faithful:
                detail = "fabricated: " + "; ".join(j["unsupported"][:3])

        passed = action_ok and faithful
        # Critical: answered when it should have escalated, OR fabricated, OR explicitly flagged.
        critical = (expected == "escalate" and answered) or (answered and not faithful) or c.get("critical", False)
        if not detail:
            detail = "ok" if passed else ("answered but should escalate" if (expected == "escalate" and answered)
                                          else "escalated but should answer")
        suite.results.append(CaseResult(c["id"], passed, critical and not passed, expected, action, detail))
    return suite


def run_classify(model: Model, cases: list[dict], skills_root: Path = SKILLS_ROOT) -> SuiteResult:
    system = _classify_system(skills_root)
    suite = SuiteResult("classify")
    for c in cases:
        expected = c["expect"]
        try:
            out = extract_json(model([
                {"role": "system", "content": system},
                {"role": "user", "content": f"CREATOR MESSAGE:\n{c['message']}"},
            ]))
            got = out.get("decision", "")
        except ValueError as e:
            got = f"parse_error:{e}"
        passed = got == expected
        suite.results.append(CaseResult(c["id"], passed, c.get("critical", False) and not passed, expected, got))
    return suite


def run_moderation(model: Model, cases: list[dict], skills_root: Path = SKILLS_ROOT) -> SuiteResult:
    system = _moderation_system(skills_root)
    suite = SuiteResult("moderation")
    for c in cases:
        accept = c["expect"] if isinstance(c["expect"], list) else [c["expect"]]
        try:
            out = extract_json(model([
                {"role": "system", "content": system},
                {"role": "user", "content": f"MESSAGE:\n{c['message']}"},
            ]))
            got = out.get("category", "")
        except ValueError as e:
            got = f"parse_error:{e}"
        passed = got in accept
        # Missing a scam is critical (safety); other misses are quality.
        critical = ("scam" in accept) and not passed
        suite.results.append(CaseResult(c["id"], passed, critical, "|".join(accept), got))
    return suite


def run_all(
    model: Model,
    judge: Model,
    *,
    cases_dir: Path = CASES_DIR,
    knowledge_dir: Path = DEFAULT_KNOWLEDGE,
    skills_root: Path = SKILLS_ROOT,
    min_pass_rate: float = MIN_PASS_RATE,
) -> EvalReport:
    kb = load_kb(knowledge_dir)
    return EvalReport(
        suites=[
            run_grounding(model, judge, load_cases(cases_dir / "grounding.jsonl"), kb, skills_root),
            run_classify(model, load_cases(cases_dir / "classify.jsonl"), skills_root),
            run_moderation(model, load_cases(cases_dir / "moderation.jsonl"), skills_root),
        ],
        min_pass_rate=min_pass_rate,
    )
