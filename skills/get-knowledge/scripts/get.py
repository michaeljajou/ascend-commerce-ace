#!/usr/bin/env python3
"""Grounding tool: return the brand's knowledge (from its YAML file) for the agent to answer from.

Replaces vector search — the knowledge is a small structured YAML doc, so we hand the model the
relevant slice (or all of it) and let it match. An **empty** result is the never-fabricate signal:
when nothing relevant is found, the answer skill must escalate.

Usage:
    python get.py --query "how do I request a sample?"   # relevant subset (or empty)
    python get.py --section commission                    # one named section
    python get.py                                         # the whole knowledge doc

Exposes `run(kb, query, section)` for tests.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

from _lib import knowledge  # noqa: E402


def run(kb: dict, query: str | None = None, section: str | None = None) -> str:
    return knowledge.run_get(kb, query=query, section=section)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Return brand knowledge (YAML) for grounding.")
    ap.add_argument("--query", help="return the subset relevant to this question (empty if none)")
    ap.add_argument("--section", help="return a single named section")
    ap.add_argument("--path", help="explicit knowledge file path (defaults to the profile's)")
    args = ap.parse_args(argv)

    try:
        kb = knowledge.load_knowledge(args.path)
    except ImportError:
        # The agent's sandbox has no PyYAML (same story as _lib/brand.py). Grounding
        # doesn't need the parsed dict — it needs the knowledge in front of the model,
        # and the file is small. Hand back the whole thing raw: worse token economy than
        # the matched subset, but never a crash, and never a false "no grounded match →
        # escalate" empty. QA 2026-07-23: this exact crash cost a creator their answer —
        # the sweep agent spent its whole budget hunting the file by hand and died one
        # call short of posting the reply it had already written.
        print(knowledge.knowledge_path(args.path).read_text(encoding="utf-8"))
        return 0
    out = run(kb, query=args.query, section=args.section)
    print(out)  # empty output = no grounded match → escalate
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
