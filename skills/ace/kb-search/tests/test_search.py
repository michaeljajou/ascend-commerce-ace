import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import search  # noqa: E402

from _lib import store  # noqa: E402
from _lib.embeddings import hashing_embedder  # noqa: E402
from _lib.models import Chunk  # noqa: E402


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    embed = hashing_embedder()
    store.upsert_document(c, "faq", "Creator FAQ")
    texts = [
        "To request a sample, post your shipping address in the samples channel.",
        "Commission is 20 percent, paid monthly on the 15th.",
    ]
    store.replace_chunks(
        c, "faq",
        [Chunk(document_id="faq", ord=i, text=t, embedding=embed([t])[0]) for i, t in enumerate(texts)],
    )
    yield c
    c.close()


def test_run_search_returns_results_for_known_question(conn):
    results = search.run_search(conn, "how do I request a sample", hashing_embedder(), min_score=0.05)
    assert results
    assert "sample" in results[0]["text"].lower()
    assert results[0]["title"] == "Creator FAQ"


def test_run_search_returns_empty_for_unknown_question(conn):
    results = search.run_search(
        conn, "what is your refund policy for enterprise SLAs", hashing_embedder(), min_score=0.5
    )
    assert results == []  # never-fabricate signal → caller must escalate
