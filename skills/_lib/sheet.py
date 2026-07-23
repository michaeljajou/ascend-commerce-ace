"""Append creator records to the team's Google Sheet (stdlib only, no OAuth).

Why a webhook instead of the Sheets API: the Sheets API needs a service account,
a key file on the VPS, per-brand sharing, and token refresh. A Google Apps Script
Web App is one URL the team creates in 2 minutes, needs no credentials on our side,
and the team owns the sheet outright. The URL goes in the brand config as
``ace.onboarding.sheet_webhook``; if it's absent, syncing is simply skipped (the
SQLite store is always the source of truth, and export_creators.py can backfill).

Apps Script to paste (Extensions → Apps Script → Deploy → Web app, execute as
yourself, access "Anyone"):

    function doPost(e) {
      const row = JSON.parse(e.postData.contents);
      const sheet = SpreadsheetApp.getActiveSheet();
      if (sheet.getLastRow() === 0) {
        sheet.appendRow(["Timestamp", "Brand", "Discord", "TikTok", "Email",
                         "Phone", "Discord ID", "Status"]);
      }
      sheet.appendRow([row.timestamp, row.brand, row.handle, row.tiktok,
                       row.email, row.phone, row.discord_id, row.status]);
      return ContentService.createTextOutput("ok");
    }
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def profile_dir() -> Path:
    from . import brand

    return brand.profile_dir()


def brand_config(profile: Path | None = None) -> dict:
    """The brand's ace config — via the PyYAML-free loader; see ``_lib/brand.py``."""
    from . import brand

    return brand.config(profile)


def webhook_url(ace: dict) -> str | None:
    return (ace.get("onboarding") or {}).get("sheet_webhook") or None


def append_row(url: str, row: dict, timeout: int = 15) -> bool:
    """POST one row. Returns success; never raises — a sheet outage must not block
    a creator's onboarding (the store already has the record)."""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(row).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "ace-sheet/0.1"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"sheet: append failed ({exc}) — the record is still in the store; "
              "re-sync later with export_creators.py --push", file=sys.stderr)
        return False


def sync_creator(row: dict, *, status: str = "onboarded", profile: Path | None = None) -> bool:
    """Push one creator record to the brand's sheet. No webhook configured → skip."""
    import time

    ace = brand_config(profile)
    url = webhook_url(ace)
    if not url:
        return False
    return append_row(url, {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "brand": ace.get("brand_name") or ace.get("brand_id") or "",
        "handle": row.get("handle") or "",
        "tiktok": row.get("tiktok") or "",
        "email": row.get("email") or "",
        "phone": row.get("phone") or "",
        "discord_id": row.get("discord_id") or "",
        "status": status,
    })
