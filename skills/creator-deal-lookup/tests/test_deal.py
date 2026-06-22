import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import deal  # noqa: E402

from _lib import store  # noqa: E402
from _lib.models import Deal  # noqa: E402


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


def test_found_deal_returns_terms(conn):
    store.upsert_deal(conn, Deal(creator_handle="@ava", terms={"rate": 500, "videos": 4, "due": "2026-07-01"}))
    out = deal.run_deal(conn, "@ava")
    assert out["found"] is True
    assert out["terms"]["rate"] == 500
    assert out["terms"]["videos"] == 4


def test_missing_deal_is_never_fabricate_signal(conn):
    out = deal.run_deal(conn, "@nobody")
    assert out == {"found": False, "handle": "@nobody"}
