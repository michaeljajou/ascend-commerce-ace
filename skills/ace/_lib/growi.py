"""Growi results client — pulls campaign/challenge results for winner announcements.

`parse_results` is pure and unit-testable; `fetch_results` performs the live HTTP call
(lazy `httpx` import). Wired up fully in Phase 5.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CampaignResults:
    campaign: str
    winners: list[dict] = field(default_factory=list)  # [{handle, prize, metric}]
    top_performers: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def parse_results(payload: dict) -> CampaignResults:
    """Normalize a Growi results payload into a CampaignResults. Pure → testable with fixtures."""
    return CampaignResults(
        campaign=payload.get("campaign") or payload.get("name") or "Campaign",
        winners=payload.get("winners", []),
        top_performers=payload.get("top_performers", []),
        stats=payload.get("stats", {}),
    )


def fetch_results(base_url: str, project: str, api_key: str | None = None) -> CampaignResults:
    """Fetch + parse results from Growi (live runtime path; Phase 5)."""
    import os

    import httpx

    api_key = api_key or os.environ.get("GROWI_API_KEY")
    resp = httpx.get(
        f"{base_url.rstrip('/')}/api/projects/{project}/results",
        headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        timeout=60.0,
    )
    resp.raise_for_status()
    return parse_results(resp.json())
