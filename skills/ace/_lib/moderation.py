"""Moderation tier resolution — the 3-tier escalation state machine (pure, testable).

Maps a creator's recent moderation history + the detected category to the next tier and action.
Severe categories (scams, severe content) jump straight to Final regardless of history.
"""

from __future__ import annotations

from dataclasses import dataclass

FRIENDLY = "friendly"
FORMAL = "formal"
FINAL = "final"

# Categories that bypass the ladder and go straight to Final.
SEVERE_CATEGORIES = frozenset({"scam", "severe", "impersonation", "phishing"})
# All recognized detection categories (negative sentiment, violations, scams, off-topic).
CATEGORIES = frozenset(
    {"negative_sentiment", "policy_violation", "off_topic", *SEVERE_CATEGORIES}
)


@dataclass
class Decision:
    tier: str
    action: str          # short action code the moderate-message skill executes
    notify_team: bool
    redirect_thread: bool  # community-chat negativity → move to a private thread


def resolve(category: str, prior_count: int, channel: str | None = None) -> Decision:
    """Decide the moderation response.

    prior_count = this creator's moderation events within the lookback window (e.g. 24h).
    """
    if category not in CATEGORIES:
        raise ValueError(f"unknown moderation category: {category!r}")

    redirect = category == "negative_sentiment" and channel == "community-chat"

    if category in SEVERE_CATEGORIES:
        return Decision(FINAL, "timeout_delete_notify", notify_team=True, redirect_thread=False)

    if prior_count <= 0:
        # First minor issue: empathize, offer help via DM/private thread, optionally flag.
        return Decision(FRIENDLY, "empathize_offer_help", notify_team=False, redirect_thread=redirect)
    if prior_count == 1:
        # Repeated/moderate: DM guidelines reminder + notify team.
        return Decision(FORMAL, "dm_guidelines_notify", notify_team=True, redirect_thread=redirect)
    # Continued violations: auto-timeout + delete + notify immediately.
    return Decision(FINAL, "timeout_delete_notify", notify_team=True, redirect_thread=False)
