import math

import pytest

from _lib import store
from _lib.embeddings import hashing_embedder
from _lib.models import ANSWERED, ESCALATED, Chunk, Creator, Deal


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


def test_pack_unpack_roundtrip():
    vec = [0.1, -0.2, 0.3, 0.0]
    out = store.unpack_embedding(store.pack_embedding(vec))
    assert all(math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6) for a, b in zip(vec, out))


def test_cosine_bounds():
    assert math.isclose(store.cosine([1, 0], [1, 0]), 1.0)
    assert math.isclose(store.cosine([1, 0], [0, 1]), 0.0)
    assert store.cosine([], [1]) == 0.0


def _ingest(conn, doc_id, title, texts):
    embed = hashing_embedder()
    store.upsert_document(conn, doc_id, title)
    store.replace_chunks(
        conn,
        doc_id,
        [Chunk(document_id=doc_id, ord=i, text=t, embedding=embed([t])[0]) for i, t in enumerate(texts)],
    )


def test_search_returns_relevant_hit(conn):
    _ingest(conn, "faq", "Creator FAQ", [
        "To request a sample, post in the samples channel with your address.",
        "Commission is paid monthly on the 15th.",
    ])
    qvec = hashing_embedder()(["how do I request a sample"])[0]
    hits = store.search(conn, qvec, k=3, min_score=0.05)
    assert hits
    assert "sample" in hits[0].text.lower()
    assert hits[0].title == "Creator FAQ"


def test_search_returns_empty_on_no_match(conn):
    _ingest(conn, "faq", "Creator FAQ", ["Commission is paid monthly on the 15th."])
    qvec = hashing_embedder()(["what is the airspeed velocity of a swallow"])[0]
    hits = store.search(conn, qvec, k=3, min_score=0.5)
    assert hits == []  # the never-fabricate signal


def test_replace_chunks_is_idempotent(conn):
    _ingest(conn, "faq", "FAQ", ["one", "two", "three"])
    _ingest(conn, "faq", "FAQ", ["one", "two"])  # re-ingest with fewer
    n = conn.execute("SELECT COUNT(*) n FROM chunks WHERE document_id='faq'").fetchone()["n"]
    assert n == 2


def test_creator_and_deal_roundtrip(conn):
    store.upsert_creator(conn, Creator(handle="@ava", tiktok="ava.tt", email="a@x.com"))
    got = store.get_creator(conn, "@ava")
    assert got and got.tiktok == "ava.tt"

    store.upsert_deal(conn, Deal(creator_handle="@ava", terms={"rate": 500, "videos": 4}))
    deal = store.get_deal(conn, "@ava")
    assert deal and deal.terms["rate"] == 500


def test_metrics_and_feedback(conn):
    iid = store.log_interaction(conn, status=ANSWERED, question="q", answer="a")
    store.log_interaction(conn, status=ESCALATED, question="q2")
    store.log_feedback(conn, iid, "up")
    m = store.metrics_since(conn, 0.0)
    assert m["total"] == 2
    assert m["answered"] == 1 and m["escalated"] == 1
    assert m["thumbs_up"] == 1
    assert m["answer_rate"] == 0.5


def test_feedback_validates_value(conn):
    iid = store.log_interaction(conn, status=ANSWERED)
    with pytest.raises(ValueError):
        store.log_feedback(conn, iid, "sideways")
