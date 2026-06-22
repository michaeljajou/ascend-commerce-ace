#!/usr/bin/env python3
"""Run the live LLM-judged eval gate against OpenRouter and exit non-zero on failure.

Requires OPENROUTER_API_KEY. Optional: ACE_EVAL_MODEL, ACE_JUDGE_MODEL, ACE_MIN_PASS_RATE.

    OPENROUTER_API_KEY=... python tests/evals/run.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_eval  # noqa: E402
from model import DEFAULT_JUDGE_MODEL, openrouter_model  # noqa: E402


def main() -> int:
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set — cannot run the live eval.", file=sys.stderr)
        return 2
    model = openrouter_model()
    judge = openrouter_model(model=os.environ.get("ACE_JUDGE_MODEL", DEFAULT_JUDGE_MODEL))
    min_rate = float(os.environ.get("ACE_MIN_PASS_RATE", llm_eval.MIN_PASS_RATE))
    report = llm_eval.run_all(model, judge, min_pass_rate=min_rate)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
