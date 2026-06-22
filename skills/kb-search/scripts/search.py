#!/usr/bin/env python3
"""Grounding tool: search the active profile's knowledge base.

The agent runs this mid-reasoning when it needs facts to answer. It prints JSON:
    {"results": [{"text", "score", "title", ...}, ...]}
An **empty** results list is meaningful — it is the never-fabricate signal. When results are
empty, the answer skill must escalate rather than invent.

Usage:
    python search.py --query "how do I request a sample?" [--k 5] [--min-score 0.25]

Exposes `run_search(conn, query, embedder, k, min_score)` for tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

from _lib import store  # noqa: E402
from _lib.embeddings import Embedder, get_embedder  # noqa: E402


def run_search(
    conn,
    query: str,
    embedder: Embedder,
    *,
    k: int = 5,
    min_score: float = 0.25,
) -> list[dict]:
    """Return JSON-ready hit dicts (possibly empty → escalate)."""
    [query_vec] = embedder([query])
    hits = store.search(conn, query_vec, k=k, min_score=min_score)
    return [h.to_json() for h in hits]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Search the brand knowledge base.")
    ap.add_argument("--query", required=True)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--min-score", type=float, default=0.25)
    args = ap.parse_args(argv)

    conn = store.connect()
    results = run_search(conn, args.query, get_embedder(), k=args.k, min_score=args.min_score)
    print(json.dumps({"results": results}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
