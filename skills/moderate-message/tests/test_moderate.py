import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import moderate  # noqa: E402

from _lib import store  # noqa: E402


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


def test_escalation_ladder_accumulates(conn):
    first = moderate.run_moderate(conn, "@ava", "policy_violation", "community-chat", now=1000)
    assert first["tier"] == "friendly" and first["prior_count"] == 0

    second = moderate.run_moderate(conn, "@ava", "policy_violation", "community-chat", now=2000)
    assert second["tier"] == "formal" and second["notify_team"] is True

    third = moderate.run_moderate(conn, "@ava", "policy_violation", "community-chat", now=3000)
    assert third["tier"] == "final" and third["action"] == "timeout_delete_notify"


def test_negativity_in_community_chat_redirects(conn):
    out = moderate.run_moderate(conn, "@ava", "negative_sentiment", "community-chat", now=1000)
    assert out["redirect_thread"] is True


def test_scam_is_immediately_final(conn):
    out = moderate.run_moderate(conn, "@bo", "scam", "community-chat", now=1000)
    assert out["tier"] == "final" and out["notify_team"] is True


def test_event_is_recorded(conn):
    moderate.run_moderate(conn, "@ava", "off_topic", "community-chat", now=1000)
    assert store.recent_moderation_count(conn, "@ava", since_ts=0.0) == 1
