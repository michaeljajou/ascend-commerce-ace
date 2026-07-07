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


def test_retry_counts_and_persists(conn):
    onboarding.start(conn, "@ava", now=100.0)
    assert onboarding.retry(conn, "@ava")["retries"] == 1
    assert onboarding.retry(conn, "@ava")["retries"] == 2
    assert onboarding.status(conn, "@ava")["retries"] == 2


def test_guided_starts_the_nudge_clock(conn):
    onboarding.start(conn, "@ava", now=100.0)
    onboarding.set_fields(conn, "@ava", tiktok="ava.tt", email="a@x.com")
    onboarding.complete(conn, "@ava", now=200.0)
    out = onboarding.guided(conn, "@ava", now=300.0)
    assert out["state"] == "guided"
    row = onboarding.status(conn, "@ava")
    assert row["guided_at"] == "300.0"
    assert row["last_active_at"] is None      # engagement clock starts fresh


def test_reset_returns_to_start_keeping_identity(conn):
    onboarding.start(conn, "@ava", now=100.0)
    onboarding.set_fields(conn, "@ava", tiktok="ava.tt", email="a@x.com")
    onboarding.complete(conn, "@ava")
    onboarding.guided(conn, "@ava", now=300.0)
    store.update_onboarding(conn, "@ava", discord_id="123", thread_id="th1", retries=2)
    out = onboarding.reset(conn, "@ava", now=400.0)
    assert out["reset"] is True
    row = onboarding.status(conn, "@ava")
    assert row["onboarding_state"] == "new"   # 'new' = the tick re-onboards with a fresh thread
    assert row["tiktok"] is None and row["email"] is None and row["retries"] == 0
    assert row["guided_at"] is None and row["nudged_at"] is None
    assert row["thread_id"] == "th1"          # kept so the tick can archive the old thread


def test_resolve_and_flag(conn):
    onboarding.start(conn, "@ava", now=100.0)
    onboarding.flag(conn, "@ava")
    assert onboarding.status(conn, "@ava")["onboarding_state"] == "flagged"
    onboarding.resolve(conn, "@ava", now=500.0)
    row = onboarding.status(conn, "@ava")
    assert row["onboarding_state"] == "resolved" and row["resolved_at"] == "500.0"


def test_status_unknown_creator(conn):
    assert onboarding.status(conn, "@ghost")["error"] == "not found"


def test_stats_shape(conn):
    onboarding.start(conn, "@a", now=1.0)
    onboarding.retry(conn, "@a")
    store.update_onboarding(conn, "@a", onboarding_state="active", nudged_at="2.0")
    onboarding.start(conn, "@b", now=1.0)
    store.update_onboarding(conn, "@b", onboarding_state="active")
    s = store.onboarding_stats(conn)
    assert s["active_after_nudge"] == 1
    assert s["active_without_nudge"] == 1
    assert s["had_invalid_input"] == 1


def test_test_mode_toggle(tmp_path):
    import yaml
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"ace": {"brand_id": "x"}}), encoding="utf-8")
    onboarding.set_test_mode(tmp_path, True)
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert cfg["ace"]["onboarding"]["test_mode"] is True
    assert cfg["ace"]["brand_id"] == "x"      # rest of config untouched
    onboarding.set_test_mode(tmp_path, False)
    assert yaml.safe_load((tmp_path / "config.yaml").read_text())["ace"]["onboarding"]["test_mode"] is False
