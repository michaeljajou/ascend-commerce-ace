import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import onboarding  # noqa: E402

from _lib import store  # noqa: E402


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


def test_full_onboarding_flow(conn):
    onboarding.start(conn, "@ava", now=100.0)
    assert store.get_creator(conn, "@ava").onboarding_state == onboarding.COLLECTING

    onboarding.set_fields(conn, "@ava", tiktok="ava.tt", email="a@x.com")
    out = onboarding.complete(conn, "@ava", role="creator", now=200.0)
    assert out["state"] == onboarding.COMPLETE

    c = store.get_creator(conn, "@ava")
    assert c.onboarding_state == "complete"
    assert c.role == "creator"
    assert c.last_active_at == "200.0"


def test_complete_requires_tiktok_and_email(conn):
    onboarding.start(conn, "@bo", now=100.0)
    with pytest.raises(ValueError):
        onboarding.complete(conn, "@bo")


def test_complete_unknown_creator_raises(conn):
    with pytest.raises(ValueError):
        onboarding.complete(conn, "@ghost")
