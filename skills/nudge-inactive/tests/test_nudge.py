import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nudge  # noqa: E402

from _lib import brand, store  # noqa: E402
from _lib.models import Creator  # noqa: E402

NOW = 1_000_000.0
DAY = 86_400.0


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    for h in ("@stale", "@mid", "@fresh", "@new"):
        state = "new" if h == "@new" else "complete"
        store.upsert_creator(c, Creator(handle=h, onboarding_state=state))
    store.mark_active(c, "@stale", ts=NOW - 8 * DAY)   # > 7d  → left alone
    store.mark_active(c, "@mid", ts=NOW - 3 * DAY)     # 48h–7d → nudge
    store.mark_active(c, "@fresh", ts=NOW - 3600)      # recent → nothing
    store.mark_active(c, "@new", ts=NOW - 10 * DAY)    # inactive but not onboarded → excluded
    yield c
    c.close()


def test_nudges_the_48h_window_and_leaves_long_quiet_creators_alone(conn):
    """Requested 2026-10-06: the 7-day "still inactive" Slack flag is gone. #ace-escalations
    is for posts that need the team to act, and a creator who went quiet is not one."""
    out = nudge.run_nudges(conn, now=NOW, nudge_after_h=48, max_inactive_h=168)
    assert out == {"nudge": ["@mid"]}                     # no "flag" bucket at all


def test_new_creators_are_not_nudged(conn):
    out = nudge.run_nudges(conn, now=NOW)
    assert "@new" not in out["nudge"]


def test_cli_has_no_flag_option_left(capsys, monkeypatch):
    monkeypatch.setattr(brand, "feature_enabled", lambda name, profile=None: True)
    real_connect = store.connect
    monkeypatch.setattr(store, "connect", lambda *a, **k: real_connect(":memory:"))
    with pytest.raises(SystemExit):
        nudge.main(["--flag-after-h", "168"])
    assert "unrecognized arguments" in capsys.readouterr().err


def test_disabled_engagement_exits_before_opening_the_store(monkeypatch, capsys):
    monkeypatch.setattr(brand, "feature_enabled", lambda name, profile=None: False)
    monkeypatch.setattr(store, "connect",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("store read")))
    assert nudge.main([]) == 0
    assert __import__("json").loads(capsys.readouterr().out)["disabled"] == "engagement"
