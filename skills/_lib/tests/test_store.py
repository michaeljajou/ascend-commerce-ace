import pytest

from _lib import store
from _lib.models import ANSWERED, ESCALATED, Creator, Deal


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


def test_creator_roundtrip(conn):
    store.upsert_creator(conn, Creator(handle="@ava", tiktok="ava.tt", email="a@x.com"))
    got = store.get_creator(conn, "@ava")
    assert got and got.tiktok == "ava.tt"


def test_deal_roundtrip(conn):
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
