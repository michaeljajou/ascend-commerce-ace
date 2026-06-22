import pytest

from _lib import store
from _lib.models import Creator


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


def test_onboarding_state_transition(conn):
    store.upsert_creator(conn, Creator(handle="@ava", onboarding_state="new"))
    store.set_onboarding_state(conn, "@ava", "complete")
    assert store.get_creator(conn, "@ava").onboarding_state == "complete"


def test_list_inactive_creators(conn):
    # @ava completed onboarding but never active → inactive; @bo active recently → not inactive.
    store.upsert_creator(conn, Creator(handle="@ava", onboarding_state="complete"))
    store.upsert_creator(conn, Creator(handle="@bo", onboarding_state="complete"))
    store.mark_active(conn, "@bo", ts=1000.0)

    inactive = store.list_inactive_creators(conn, since_ts=500.0)
    handles = {c.handle for c in inactive}
    assert "@ava" in handles      # never active
    assert "@bo" not in handles   # active at ts=1000 >= 500

    # raise the cutoff so even @bo counts as inactive
    later = {c.handle for c in store.list_inactive_creators(conn, since_ts=2000.0)}
    assert {"@ava", "@bo"} <= later


def test_inactive_respects_onboarding_state_filter(conn):
    store.upsert_creator(conn, Creator(handle="@new", onboarding_state="new"))
    # default filter is ('complete',) → a 'new' creator is not nudged
    assert store.list_inactive_creators(conn, since_ts=9e9) == []


def test_recent_moderation_count(conn):
    store.record_moderation(conn, tier="friendly", action="x", creator_handle="@ava", ts=100.0)
    store.record_moderation(conn, tier="formal", action="y", creator_handle="@ava", ts=200.0)
    store.record_moderation(conn, tier="friendly", action="z", creator_handle="@bo", ts=150.0)
    assert store.recent_moderation_count(conn, "@ava", since_ts=0.0) == 2
    assert store.recent_moderation_count(conn, "@ava", since_ts=150.0) == 1
    assert store.recent_moderation_count(conn, "@bo", since_ts=0.0) == 1
