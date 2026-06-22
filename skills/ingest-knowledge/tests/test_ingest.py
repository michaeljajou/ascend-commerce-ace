import sys
from pathlib import Path

import pytest

# import the script under test (it adds skills to sys.path for _lib on import)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ingest  # noqa: E402

from _lib import store  # noqa: E402
from _lib.embeddings import hashing_embedder  # noqa: E402

FIXTURE_BRAND = Path(__file__).resolve().parent / "fixtures" / "brand"


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


def test_run_ingest_loads_documents_and_chunks(conn):
    summary = ingest.run_ingest(conn, str(FIXTURE_BRAND), hashing_embedder(), kind="local")
    assert summary["documents"] == 2  # faq.md + payments.md
    assert summary["chunks"] >= 2

    docs = conn.execute("SELECT COUNT(*) n FROM documents").fetchone()["n"]
    chunks = conn.execute("SELECT COUNT(*) n FROM chunks").fetchone()["n"]
    assert docs == 2 and chunks == summary["chunks"]


def test_ingest_is_idempotent(conn):
    embed = hashing_embedder()
    ingest.run_ingest(conn, str(FIXTURE_BRAND), embed, kind="local")
    first = conn.execute("SELECT COUNT(*) n FROM chunks").fetchone()["n"]
    ingest.run_ingest(conn, str(FIXTURE_BRAND), embed, kind="local")  # re-ingest
    second = conn.execute("SELECT COUNT(*) n FROM chunks").fetchone()["n"]
    assert first == second  # replaced, not duplicated


def test_ingested_knowledge_is_searchable(conn):
    embed = hashing_embedder()
    ingest.run_ingest(conn, str(FIXTURE_BRAND), embed, kind="local")
    qvec = embed(["how do I request a sample"])[0]
    hits = store.search(conn, qvec, k=3, min_score=0.05)
    assert hits and "sample" in hits[0].text.lower()
