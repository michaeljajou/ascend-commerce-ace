"""sheet.py: creator records → the team's Google Sheet, failure-tolerant."""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import sheet  # noqa: E402


def make_profile(tmp_path, *, webhook="https://script.google.com/hook"):
    ob = {"enabled": True}
    if webhook:
        ob["sheet_webhook"] = webhook
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"ace": {
        "brand_id": "pilot", "brand_name": "Pilot", "onboarding": ob}}), encoding="utf-8")
    (tmp_path / "ace").mkdir(exist_ok=True)
    return tmp_path


def test_sync_posts_a_full_brand_tagged_row(tmp_path, monkeypatch):
    make_profile(tmp_path)
    monkeypatch.setenv("ACE_DATA_DIR", str(tmp_path / "ace"))
    sent = {}
    monkeypatch.setattr(sheet, "append_row",
                        lambda url, row, **kw: sent.update(url=url, row=row) or True)
    assert sheet.sync_creator({"handle": "@ava", "tiktok": "ava.tt", "email": "a@x.com",
                               "phone": "+1555", "discord_id": "77"}) is True
    assert sent["url"] == "https://script.google.com/hook"
    row = sent["row"]
    assert row["brand"] == "Pilot" and row["handle"] == "@ava"
    assert row["tiktok"] == "ava.tt" and row["phone"] == "+1555"
    assert row["status"] == "onboarded" and row["timestamp"]


def test_missing_optional_fields_become_empty_strings(tmp_path, monkeypatch):
    """Email/phone are skippable — the sheet gets blanks, never 'None'."""
    make_profile(tmp_path)
    monkeypatch.setenv("ACE_DATA_DIR", str(tmp_path / "ace"))
    sent = {}
    monkeypatch.setattr(sheet, "append_row", lambda url, row, **kw: sent.update(row=row) or True)
    sheet.sync_creator({"handle": "@bo", "tiktok": "bo.tt", "email": None, "phone": None})
    assert sent["row"]["email"] == "" and sent["row"]["phone"] == ""


def test_no_webhook_configured_is_a_silent_skip(tmp_path, monkeypatch):
    make_profile(tmp_path, webhook=None)
    monkeypatch.setenv("ACE_DATA_DIR", str(tmp_path / "ace"))
    assert sheet.sync_creator({"handle": "@ava"}) is False


def test_sheet_outage_never_raises(tmp_path, monkeypatch, capsys):
    """A dead webhook must not break a creator's onboarding."""
    import urllib.error

    def boom(req, timeout):
        raise urllib.error.URLError("sheet down")

    monkeypatch.setattr(sheet.urllib.request, "urlopen", boom)
    assert sheet.append_row("https://script.google.com/hook", {"handle": "@ava"}) is False
    assert "append failed" in capsys.readouterr().err
