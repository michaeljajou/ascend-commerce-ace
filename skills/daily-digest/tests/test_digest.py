import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import digest  # noqa: E402

from _lib import store  # noqa: E402
from _lib.models import ANSWERED, ESCALATED, Creator, Deal  # noqa: E402

NOW = 1_700_000_000.0


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    recent = NOW - 3600  # within the 24h window
    iid = store.log_interaction(c, status=ANSWERED, ts=recent, question="q1", answer="a1")
    store.log_interaction(c, status=ANSWERED, ts=recent, question="q2", answer="a2")
    store.log_interaction(c, status=ESCALATED, ts=recent, question="q3")
    store.log_feedback(c, iid, "up", ts=recent)
    store.record_moderation(c, tier="friendly", action="x", creator_handle="@x", ts=recent)
    store.upsert_creator(c, Creator(handle="@new", onboarding_state="collecting", joined_at=str(recent)))
    due = (datetime.fromtimestamp(NOW).date() + timedelta(days=3)).isoformat()
    store.upsert_deal(c, Deal(creator_handle="@ava", terms={"rate": 500, "due": due}))
    yield c
    c.close()


def test_build_digest_aggregates(conn):
    d = digest.build_digest(conn, now=NOW)
    m = d["interactions"]
    assert m["total"] == 3 and m["answered"] == 2 and m["escalated"] == 1
    assert m["thumbs_up"] == 1
    assert m["moderation_actions"] == 1
    assert len(d["new_members"]) == 1
    assert len(d["upcoming_deadlines"]) == 1 and d["upcoming_deadlines"][0]["in_days"] == 3


def test_render_digest_text(conn):
    text = digest.render_digest(digest.build_digest(conn, now=NOW))
    assert "Interactions: 3" in text
    assert "Answer rate: 66%" in text  # 2/3
    assert "Upcoming deadlines" in text


def test_far_off_deadline_excluded(conn):
    far = (datetime.fromtimestamp(NOW).date() + timedelta(days=30)).isoformat()
    store.upsert_deal(conn, Deal(creator_handle="@late", terms={"due": far}))
    d = digest.build_digest(conn, now=NOW, deadline_days=7)
    handles = {x["handle"] for x in d["upcoming_deadlines"]}
    assert "@late" not in handles
