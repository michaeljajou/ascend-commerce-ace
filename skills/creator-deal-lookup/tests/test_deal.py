import json
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


def test_disabled_general_qa_refuses_before_opening_store(tmp_path, monkeypatch, capsys):
    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    (ace_dir / "brand.json").write_text(
        json.dumps({"features": {"general_qa": False}}), encoding="utf-8"
    )
    monkeypatch.setattr(store, "connect",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("store read")))
    monkeypatch.setenv("ACE_DATA_DIR", str(ace_dir))

    assert deal.main(["--handle", "@ava"]) == 0
    assert json.loads(capsys.readouterr().out) == {"disabled": "general_qa"}


def test_cli_rejects_a_cross_profile_policy_override(tmp_path):
    with pytest.raises(SystemExit):
        deal.main(["--profile-dir", str(tmp_path), "--handle", "@ava"])
