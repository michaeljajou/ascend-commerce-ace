"""Golden eval gate — the never-fabricate / grounding boundary (offline).

The OFFLINE proxy for the gate: using only the structured knowledge YAML (no model, no network),
it asserts that questions which *should* be answerable resolve to grounded knowledge, and questions
which *should not* resolve to nothing (→ the agent must escalate, never fabricate).

The LIVE version (an LLM judging full answers) lives in `llm_eval.py` / `run.py`; this offline gate
runs in CI on every change to catch grounding regressions in the knowledge file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from _lib import knowledge


@dataclass
class GateResult:
    passed: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def _load_cases(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def run_gate(knowledge_path: Path, cases_dir: Path) -> GateResult:
    kb = knowledge.load_knowledge(knowledge_path)
    result = GateResult()

    for q in _load_cases(cases_dir / "should_answer.txt"):
        if knowledge.find(kb, q):
            result.passed += 1
        else:
            result.failures.append(f"should_answer but found NO grounded knowledge: {q!r}")

    for q in _load_cases(cases_dir / "should_escalate.txt"):
        if not knowledge.find(kb, q):
            result.passed += 1
        else:
            result.failures.append(f"should_escalate but matched knowledge (would fabricate): {q!r}")

    return result
