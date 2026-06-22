"""Plain dataclasses for Ace's per-profile data.

Dataclasses (not pydantic) keep the core dependency-free so the unit tests run on the stdlib.
These mirror the tables created in ``store.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chunk:
    """A retrievable slice of a brand document."""

    document_id: str
    ord: int
    text: str
    embedding: list[float] = field(default_factory=list)
    id: int | None = None


@dataclass
class SearchHit:
    """A `kb_search` result: a chunk plus its similarity score and source title."""

    text: str
    score: float
    title: str
    document_id: str
    ord: int

    def to_json(self) -> dict:
        return {
            "text": self.text,
            "score": round(self.score, 4),
            "title": self.title,
            "document_id": self.document_id,
            "ord": self.ord,
        }


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
