"""Golden eval gate — the never-fabricate / grounding boundary.

This is the OFFLINE proxy for the gate: using the deterministic hashing embedder (no network,
no LLM), it asserts that questions which *should* be answerable retrieve grounded chunks, and
questions which *should not* retrieve nothing (→ the agent must escalate, never fabricate).

The LIVE version (an LLM judging full answers in a real Hermes profile) is wired up in the
Phase 0 spike; this offline gate runs in CI on every change to catch retrieval regressions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from _lib import store
from _lib.embeddings import hashing_embedder

# Score floor for the offline gate. Real profiles tune min_score per brand.
GATE_MIN_SCORE = 0.2


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


def _build_kb(knowledge_dir: Path):
    """Ingest a brand's knowledge fixtures into an in-memory store (deterministic embedder)."""
    from _lib import chunking
    from _lib.models import Chunk

    embed = hashing_embedder()
    conn = store.connect(":memory:")
    for md in sorted(knowledge_dir.rglob("*.md")):
        doc_id = str(md.relative_to(knowledge_dir))
        # Smaller chunks so each FAQ topic stays distinct (concentrates topical matches).
        texts = chunking.chunk_text(md.read_text(encoding="utf-8"), max_chars=200, overlap=0)
        store.upsert_document(conn, doc_id, md.stem)
        store.replace_chunks(
            conn, doc_id,
            [Chunk(document_id=doc_id, ord=i, text=t, embedding=embed([t])[0]) for i, t in enumerate(texts)],
        )
    return conn, embed


def run_gate(knowledge_dir: Path, cases_dir: Path, min_score: float = GATE_MIN_SCORE) -> GateResult:
    conn, embed = _build_kb(knowledge_dir)
    result = GateResult()

    for q in _load_cases(cases_dir / "should_answer.txt"):
        hits = store.search(conn, embed([q])[0], k=5, min_score=min_score)
        if hits:
            result.passed += 1
        else:
            result.failures.append(f"should_answer but got NO grounded results: {q!r}")

    for q in _load_cases(cases_dir / "should_escalate.txt"):
        hits = store.search(conn, embed([q])[0], k=5, min_score=min_score)
        if not hits:
            result.passed += 1
        else:
            result.failures.append(
                f"should_escalate but retrieved (would fabricate): {q!r} -> top={hits[0].score:.2f}"
            )

    conn.close()
    return result
