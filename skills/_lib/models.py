"""Plain dataclasses for Ace's per-profile operational data.

Dataclasses (not pydantic) keep the store layer dependency-free. These mirror the tables created in
``store.py``. Brand knowledge is a YAML document (see ``knowledge.py``), not modeled here.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Creator:
    handle: str
    tiktok: str | None = None
    email: str | None = None
    role: str | None = None
    onboarding_state: str = "new"  # new | collecting | complete
    joined_at: str | None = None
    last_active_at: str | None = None
    id: int | None = None


@dataclass
class Deal:
    """A paid-collab / ambassador deal for one creator (terms held as JSON)."""

    creator_handle: str
    terms: dict = field(default_factory=dict)
    id: int | None = None


# Interaction outcomes — used for metrics + the daily digest.
ANSWERED = "answered"
ESCALATED = "escalated"
ROUTED = "routed"  # creative-strategist scope handed to the team
