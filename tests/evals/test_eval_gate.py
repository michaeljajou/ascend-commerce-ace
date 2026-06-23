"""CI gate: the grounding boundary must hold for the pilot brand fixtures."""

from pathlib import Path

import sys

# tests/evals/runner.py imports `_lib` (root conftest puts skills on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
KNOWLEDGE = REPO / "tests" / "fixtures" / "pilot-brand" / "knowledge.yaml"
CASES = Path(__file__).resolve().parent / "fixtures" / "pilot-brand"


def test_grounding_boundary_holds():
    result = runner.run_gate(KNOWLEDGE, CASES)
    assert result.ok, "Eval gate failures:\n" + "\n".join(result.failures)
    assert result.passed >= 6  # 3 should_answer + 3 should_escalate
