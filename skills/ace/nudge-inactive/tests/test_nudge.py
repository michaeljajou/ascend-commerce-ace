import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nudge  # noqa: E402

from _lib import store  # noqa: E402
from _lib.models import Creator  # noqa: E402

NOW = 1_000_000.0
DAY = 86_400.0


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    for h in ("@stale", "@mid", "@fresh", "@new"):
        state = "new" if h == "@new" else "complete"
        store.upsert_creator(c, Creator(handle=h, onboarding_state=state))
    store.mark_active(c, "@stale", ts=NOW - 8 * DAY)   # > 7d  → flag
    store.mark_active(c, "@mid", ts=NOW - 3 * DAY)     # 48h–7d → nudge
    store.mark_active(c, "@fresh", ts=NOW - 3600)      # recent → neither
    store.mark_active(c, "@new", ts=NOW - 10 * DAY)    # inactive but not onboarded → excluded
    yield c
    c.close()


def test_buckets_nudge_and_flag(conn):
    out = nudge.run_nudges(conn, now=NOW, nudge_after_h=48, flag_after_h=168)
    assert out["nudge"] == ["@mid"]
    assert out["flag"] == ["@stale"]


def test_new_creators_are_not_nudged(conn):
    out = nudge.run_nudges(conn, now=NOW)
    assert "@new" not in out["nudge"] and "@new" not in out["flag"]
