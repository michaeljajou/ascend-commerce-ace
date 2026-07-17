"""Embedded per-profile store for Ace's *operational* data (stdlib only).

One SQLite database per Hermes profile holds the brand's structured runtime data: creators, deals,
interactions, feedback, and moderation events (+ metrics derived from them).

Brand *knowledge* (brief/FAQ/commission/etc.) is NOT here — it lives as a structured YAML file the
agent reads directly (see ``knowledge.py``). This store is for things that change at runtime.

The active tenant's data dir comes from ``ACE_DATA_DIR`` (the bundle's own contract, set per tenant
by the setup skill). The core stays orchestrator-agnostic and never reads orchestrator-specific env
vars — mapping a given orchestrator's per-tenant home to ``ACE_DATA_DIR`` is the setup adapter's job.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from . import models
from .models import Creator, Deal

# --- profile/data-dir resolution -------------------------------------------------------------

DB_FILENAME = "ace.db"


def data_dir() -> Path:
    """Directory for the *active* tenant's Ace data (DB + knowledge file).

    Resolution order (first set wins):
      1. ``ACE_DATA_DIR`` — the bundle's own contract; set per tenant by the setup skill
      2. ``./data``       — local dev / test fallback

    Orchestrator-agnostic by design: the core reads only ``ACE_DATA_DIR``. For Hermes, ``setup-brand``
    derives the profile path and writes ``ACE_DATA_DIR`` into the profile's ``.env``; porting to
    another orchestrator means a different setup adapter, not a change here.
    """
    if env := os.environ.get("ACE_DATA_DIR"):
        return Path(env)
    # Hermes strips custom env vars (ACE_DATA_DIR included) from the agent's code
    # sandbox, but passes HERMES_HOME (= the profile dir). setup-brand always puts the
    # data dir at <profile>/ace, so this fallback keeps every script grounded in the
    # REAL profile store instead of silently writing into a throwaway sandbox dir —
    # the root cause of both the get.py "default path" bug and onboarding records
    # vanishing mid-conversation.
    if home := os.environ.get("HERMES_HOME"):
        return Path(home) / "ace"
    return Path.cwd() / "data"


def db_path() -> Path:
    return data_dir() / DB_FILENAME


# --- connection + schema ---------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS creators (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    handle           TEXT UNIQUE NOT NULL,
    tiktok           TEXT,
    email            TEXT,
    role             TEXT,
    onboarding_state TEXT DEFAULT 'new',
    joined_at        TEXT,
    last_active_at   TEXT
);
CREATE TABLE IF NOT EXISTS deals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_handle TEXT UNIQUE NOT NULL,
    terms_json     TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS interactions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             REAL NOT NULL,
    channel        TEXT,
    creator_handle TEXT,
    question       TEXT,
    answer         TEXT,
    status         TEXT NOT NULL            -- answered | escalated | routed
);
CREATE TABLE IF NOT EXISTS feedback (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    interaction_id INTEGER REFERENCES interactions(id) ON DELETE CASCADE,
    value          TEXT NOT NULL,           -- up | down
    ts             REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS moderation_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             REAL NOT NULL,
    creator_handle TEXT,
    channel        TEXT,
    tier           TEXT,                    -- friendly | formal | final
    action         TEXT,
    reason         TEXT
);
"""


# Columns added after the initial schema shipped (idempotent ALTERs on connect).
# The onboarding flow (Vaulty replacement) tracks its whole lifecycle on the creator row.
# NOTE: onboarding_tick.py (copied standalone into each profile's scripts/) carries a
# mirror of this list — update both together.
ONBOARDING_MIGRATIONS = [
    "ALTER TABLE creators ADD COLUMN discord_id TEXT",
    "ALTER TABLE creators ADD COLUMN thread_id TEXT",          # their private onboarding thread
    "ALTER TABLE creators ADD COLUMN retries INTEGER DEFAULT 0",
    "ALTER TABLE creators ADD COLUMN guided_at TEXT",          # guidance done → 48h nudge clock
    "ALTER TABLE creators ADD COLUMN nudged_at TEXT",
    "ALTER TABLE creators ADD COLUMN escalated_at TEXT",
    "ALTER TABLE creators ADD COLUMN escalation_channel TEXT", # Slack channel id of the post
    "ALTER TABLE creators ADD COLUMN escalation_ts TEXT",      # Slack message ts (✅ resolve poll)
    "ALTER TABLE creators ADD COLUMN resolved_at TEXT",
    "ALTER TABLE creators ADD COLUMN phone TEXT",              # optional WhatsApp/phone
]


def connect(path: str | os.PathLike | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the profile DB and ensure the schema exists.

    Pass ``":memory:"`` in tests for an isolated, disposable DB.
    """
    target = ":memory:" if path == ":memory:" else str(path or db_path())
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    for migration in ONBOARDING_MIGRATIONS:
        try:
            conn.execute(migration)
        except sqlite3.OperationalError:
            pass  # column already exists
    return conn


# --- creators --------------------------------------------------------------------------------


def upsert_creator(conn: sqlite3.Connection, creator: Creator) -> None:
    conn.execute(
        """INSERT INTO creators (handle, tiktok, email, role, onboarding_state, joined_at, last_active_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(handle) DO UPDATE SET
             tiktok=COALESCE(excluded.tiktok, creators.tiktok),
             email=COALESCE(excluded.email, creators.email),
             role=COALESCE(excluded.role, creators.role),
             onboarding_state=excluded.onboarding_state,
             last_active_at=COALESCE(excluded.last_active_at, creators.last_active_at)""",
        (
            creator.handle,
            creator.tiktok,
            creator.email,
            creator.role,
            creator.onboarding_state,
            creator.joined_at,
            creator.last_active_at,
        ),
    )
    conn.commit()


def get_creator(conn: sqlite3.Connection, handle: str) -> Creator | None:
    r = conn.execute("SELECT * FROM creators WHERE handle = ?", (handle,)).fetchone()
    if not r:
        return None
    return Creator(
        id=r["id"],
        handle=r["handle"],
        tiktok=r["tiktok"],
        email=r["email"],
        role=r["role"],
        onboarding_state=r["onboarding_state"],
        joined_at=r["joined_at"],
        last_active_at=r["last_active_at"],
    )


def set_onboarding_state(conn: sqlite3.Connection, handle: str, state: str) -> None:
    conn.execute("UPDATE creators SET onboarding_state = ? WHERE handle = ?", (state, handle))
    conn.commit()


def mark_active(conn: sqlite3.Connection, handle: str, ts: float | None = None) -> None:
    conn.execute(
        "UPDATE creators SET last_active_at = ? WHERE handle = ?",
        (str(ts if ts is not None else time.time()), handle),
    )
    conn.commit()


def list_inactive_creators(
    conn: sqlite3.Connection,
    since_ts: float,
    onboarding_states: tuple[str, ...] = ("complete",),
) -> list[Creator]:
    """Creators whose last activity is before ``since_ts`` (or never), in the given states.

    Used by `nudge-inactive`. ``last_active_at`` is stored as a stringified epoch.
    """
    placeholders = ",".join("?" for _ in onboarding_states)
    rows = conn.execute(
        f"""SELECT * FROM creators
            WHERE onboarding_state IN ({placeholders})
              AND (last_active_at IS NULL OR CAST(last_active_at AS REAL) < ?)""",
        (*onboarding_states, since_ts),
    ).fetchall()
    return [
        Creator(
            id=r["id"], handle=r["handle"], tiktok=r["tiktok"], email=r["email"], role=r["role"],
            onboarding_state=r["onboarding_state"], joined_at=r["joined_at"],
            last_active_at=r["last_active_at"],
        )
        for r in rows
    ]


# --- onboarding lifecycle (Vaulty replacement) ------------------------------------------------
# These work with the migration columns directly (dict rows) rather than the Creator dataclass,
# which stays focused on the stable core fields.


def get_onboarding(conn: sqlite3.Connection, handle: str) -> dict | None:
    r = conn.execute("SELECT * FROM creators WHERE handle = ?", (handle,)).fetchone()
    return dict(r) if r else None


def update_onboarding(conn: sqlite3.Connection, handle: str, **fields) -> None:
    """Set arbitrary onboarding columns on a creator row (column names are code-controlled)."""
    if not fields:
        return
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE creators SET {assignments} WHERE handle = ?", (*fields.values(), handle))
    conn.commit()


def onboarding_stats(conn: sqlite3.Connection) -> dict:
    """The tracking metrics from the onboarding requirements (per brand)."""
    rows = conn.execute(
        "SELECT onboarding_state, COUNT(*) n FROM creators GROUP BY onboarding_state"
    ).fetchall()
    by_state = {r["onboarding_state"]: r["n"] for r in rows}
    nudged_then_active = conn.execute(
        "SELECT COUNT(*) n FROM creators WHERE onboarding_state = 'active' AND nudged_at IS NOT NULL"
    ).fetchone()["n"]
    no_nudge_active = conn.execute(
        "SELECT COUNT(*) n FROM creators WHERE onboarding_state = 'active' AND nudged_at IS NULL"
    ).fetchone()["n"]
    retried = conn.execute(
        "SELECT COUNT(*) n FROM creators WHERE retries > 0"
    ).fetchone()["n"]
    return {
        "by_state": by_state,
        "active_without_nudge": no_nudge_active,
        "active_after_nudge": nudged_then_active,
        "escalated": by_state.get("escalated", 0) + by_state.get("resolved", 0),
        "had_invalid_input": retried,
    }


# --- deals -----------------------------------------------------------------------------------


def upsert_deal(conn: sqlite3.Connection, deal: Deal) -> None:
    import json

    conn.execute(
        """INSERT INTO deals (creator_handle, terms_json) VALUES (?, ?)
           ON CONFLICT(creator_handle) DO UPDATE SET terms_json=excluded.terms_json""",
        (deal.creator_handle, json.dumps(deal.terms)),
    )
    conn.commit()


def get_deal(conn: sqlite3.Connection, creator_handle: str) -> Deal | None:
    import json

    r = conn.execute("SELECT * FROM deals WHERE creator_handle = ?", (creator_handle,)).fetchone()
    if not r:
        return None
    return Deal(id=r["id"], creator_handle=r["creator_handle"], terms=json.loads(r["terms_json"]))


# --- interactions / feedback / moderation (metrics + digest) ---------------------------------


def log_interaction(
    conn: sqlite3.Connection,
    *,
    status: str,
    channel: str | None = None,
    creator_handle: str | None = None,
    question: str | None = None,
    answer: str | None = None,
    ts: float | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO interactions (ts, channel, creator_handle, question, answer, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ts or time.time(), channel, creator_handle, question, answer, status),
    )
    conn.commit()
    return int(cur.lastrowid)


def log_feedback(
    conn: sqlite3.Connection, interaction_id: int, value: str, ts: float | None = None
) -> None:
    if value not in ("up", "down"):
        raise ValueError("feedback value must be 'up' or 'down'")
    conn.execute(
        "INSERT INTO feedback (interaction_id, value, ts) VALUES (?, ?, ?)",
        (interaction_id, value, ts or time.time()),
    )
    conn.commit()


def record_moderation(
    conn: sqlite3.Connection,
    *,
    tier: str,
    action: str,
    creator_handle: str | None = None,
    channel: str | None = None,
    reason: str | None = None,
    ts: float | None = None,
) -> None:
    conn.execute(
        """INSERT INTO moderation_events (ts, creator_handle, channel, tier, action, reason)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ts or time.time(), creator_handle, channel, tier, action, reason),
    )
    conn.commit()


def recent_moderation_count(conn: sqlite3.Connection, handle: str, since_ts: float) -> int:
    """How many moderation events this creator has accrued since ``since_ts`` (drives tiering)."""
    return conn.execute(
        "SELECT COUNT(*) n FROM moderation_events WHERE creator_handle = ? AND ts >= ?",
        (handle, since_ts),
    ).fetchone()["n"]


def metrics_since(conn: sqlite3.Connection, since_ts: float) -> dict:
    """Aggregate counts for the daily digest / metrics, for interactions at/after ``since_ts``."""
    rows = conn.execute(
        "SELECT status, COUNT(*) n FROM interactions WHERE ts >= ? GROUP BY status",
        (since_ts,),
    ).fetchall()
    by_status = {r["status"]: r["n"] for r in rows}
    answered = by_status.get(models.ANSWERED, 0)
    escalated = by_status.get(models.ESCALATED, 0)
    routed = by_status.get(models.ROUTED, 0)
    total = answered + escalated + routed

    fb = conn.execute(
        "SELECT value, COUNT(*) n FROM feedback WHERE ts >= ? GROUP BY value", (since_ts,)
    ).fetchall()
    by_fb = {r["value"]: r["n"] for r in fb}
    up, down = by_fb.get("up", 0), by_fb.get("down", 0)

    mod = conn.execute(
        "SELECT COUNT(*) n FROM moderation_events WHERE ts >= ?", (since_ts,)
    ).fetchone()["n"]

    return {
        "total": total,
        "answered": answered,
        "escalated": escalated,
        "routed": routed,
        "answer_rate": round(answered / total, 3) if total else 0.0,
        "thumbs_up": up,
        "thumbs_down": down,
        "thumbs_up_pct": round(up / (up + down), 3) if (up + down) else None,
        "moderation_actions": mod,
    }
