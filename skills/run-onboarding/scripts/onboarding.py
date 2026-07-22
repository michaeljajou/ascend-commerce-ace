#!/usr/bin/env python3
"""Creator onboarding state (replaces Vaulty's data collection + role step).

Records the creator, captures TikTok handle + email, tracks retries, completes onboarding,
and gives the team its controls (status / reset / resolve / test-mode / stats). The
conversational guidance lives in the SKILL.md; this script just persists state so the
onboarding tick, `nudge-inactive`, and the digest can use it.

The agent needs exactly ONE of these — `answer` — for the whole collection conversation:

    python onboarding.py answer --handle @ava --text "<the creator's message, verbatim>"
    python onboarding.py guided --handle @ava    # guidance delivered → 48h clock starts

``answer`` works out which question is outstanding, validates the reply against it, saves
it or counts a retry, and reports what to ask next — assigning the Discord roles and
posting the signup card itself once nothing is left to ask. The agent supplies words and
nothing else.

That is the whole design principle here, learned one QA round at a time: every decision
left to the agent was eventually gotten wrong. It took a Discord thread's own name as a
TikTok handle, hunted for a Discord ID it was never given, and — with the correct
instructions in front of it — greeted a creator and re-asked a question they had just
answered, because a thread's first turn buries their reply under the whole skill document.

The pieces `answer` composes, still available for operator repair work:

    python onboarding.py start    --handle @ava                     # state=collecting
    python onboarding.py set      --handle @ava --tiktok "<raw>"    # one field, validated
    python onboarding.py complete --handle @ava                     # roles + Slack

Team subcommands (via admin-commands, or the CLI directly):
    python onboarding.py status   --handle @ava
    python onboarding.py retry    --handle @ava                     # manual bump; `set` is automatic
    python onboarding.py reset    --handle @ava                     # back to the start of the flow
    python onboarding.py resolve  --handle @ava                     # close an escalated case
    python onboarding.py test-mode on|off                           # compressed timers for QA
    python onboarding.py stats
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

from _lib import store  # noqa: E402
from _lib.models import Creator  # noqa: E402

NEW, COLLECTING, COMPLETE = "new", "collecting", "complete"

# Where captured creator details land for the team (override per brand with
# ace.onboarding.data_channel). Separate from #ace-escalations so signups stay
# scannable and aren't buried among escalations.
DATA_CHANNEL = "#ace-onboarding"
DEFAULT_MAX_RETRIES = 3

# --- field rules -------------------------------------------------------------------------
# These live in code, not in the prompt. A regex applies the same rule to every creator on
# every brand forever; a paragraph of prose gets re-interpreted on each turn by whichever
# model is cheapest that month. QA caught the agent accepting a Discord thread name
# ("welcome-john-2029") as a TikTok handle and never counting it as a bad answer.
TIKTOK_RE = re.compile(r"^[A-Za-z0-9_.]{1,24}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?\d[\d\s().\-]{5,19}$")
TIKTOK_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?tiktok\.com/@?([A-Za-z0-9_.]{1,24})")

# A decline is a first-class answer on the optional fields — never a retry, never argued
# with. Matched on the whole message so "skipping town" isn't read as a refusal.
SKIP_WORDS = {
    "skip", "skip it", "skipped", "no", "nope", "nah", "pass", "n/a", "na", "none",
    "no thanks", "no thank you", "rather not", "prefer not to", "prefer not to say",
    "i'd rather not", "id rather not", "next", "-",
}

OPTIONAL_FIELDS = {"email", "phone"}


def normalize(field: str, raw: str) -> tuple[str | None, str | None]:
    """Return ``(clean_value, None)``, ``("", None)`` for a skip, or ``(None, reason)``.

    ``reason`` is a short machine tag the caller turns into a friendly re-ask; it is never
    shown to a creator verbatim.
    """
    text = (raw or "").strip()
    if not text:
        return None, "blank"
    if text.lower().strip(".!") in SKIP_WORDS:
        return ("", None) if field in OPTIONAL_FIELDS else (None, "required")

    if field == "tiktok":
        if m := TIKTOK_URL_RE.search(text):
            return m.group(1), None
        candidate = text.lstrip("@").strip()
        if EMAIL_RE.match(candidate):
            return None, "looks_like_email"
        if TIKTOK_RE.match(candidate):
            return candidate, None
        # "my tiktok is @javarisjavar" — pull the @-tagged token out of a sentence. Only
        # an explicit @ counts: without it, "my tiktok is coming soon" would happily save
        # "soon". Anything vaguer goes back as a re-ask, which costs one friendly line.
        tagged = [t.lstrip("@").strip(".,!?;:\"')") for t in text.split() if t.startswith("@")]
        if len(tagged) == 1 and TIKTOK_RE.match(tagged[0]):
            return tagged[0], None
        return None, "not_a_handle"
    if field == "email":
        return (text, None) if EMAIL_RE.match(text) else (None, "not_an_email")
    if field == "phone":
        return (text, None) if PHONE_RE.match(text) else (None, "not_a_phone")
    raise ValueError(f"unknown field {field!r}")


def max_retries() -> int:
    from _lib import sheet

    ob = (sheet.brand_config() or {}).get("onboarding") or {}
    try:
        return int(ob.get("max_retries") or DEFAULT_MAX_RETRIES)
    except (TypeError, ValueError):
        return DEFAULT_MAX_RETRIES


def start(conn, handle: str, now: float | None = None) -> dict:
    now = now if now is not None else time.time()
    store.upsert_creator(conn, Creator(handle=handle, onboarding_state=COLLECTING, joined_at=str(now)))
    return {"handle": handle, "state": COLLECTING}


def set_fields(conn, handle: str, tiktok: str | None = None, email: str | None = None,
               phone: str | None = None, now: float | None = None) -> dict:
    """Validate and store the creator's raw answers; count a retry on anything unusable.

    Returns ``{"ok": bool, ...}``. On ``ok: false`` the caller re-asks using ``reason``;
    once ``limit_reached`` is true the creator is already flagged and the team already
    pinged, so the caller's only job is to hand off warmly and stop asking.
    """
    existing = store.get_creator(conn, handle)
    if existing is None:
        existing = Creator(handle=handle, onboarding_state=COLLECTING,
                           joined_at=str(now if now is not None else time.time()))
    # Validate everything BEFORE writing anything, so a bad value in one field can't throw
    # away a good value the creator gave for another in the same call.
    saved: dict[str, str] = {}
    skipped: list[str] = []
    failure: tuple[str, str, str] | None = None       # (field, reason, raw)
    for field, raw in (("tiktok", tiktok), ("email", email), ("phone", phone)):
        if raw is None:
            continue
        value, reason = normalize(field, raw)
        if reason:
            failure = failure or (field, reason, raw)
        elif value:
            saved[field] = value
        else:
            skipped.append(field)

    existing.tiktok = saved.get("tiktok") or existing.tiktok
    existing.email = saved.get("email") or existing.email
    existing.onboarding_state = COLLECTING
    store.upsert_creator(conn, existing)
    # Talking to Ace IS activity — without this stamp the tick reads a creator who is
    # mid-answer as "quiet since joining" and escalates them to Slack (QA, 2026-07-22).
    store.mark_active(conn, handle, ts=now)
    if saved.get("phone"):
        store.update_onboarding(conn, handle, phone=saved["phone"])

    if failure:
        field, reason, raw = failure
        bumped = retry(conn, handle, ensure=existing)
        limit = max_retries()
        out = {"ok": False, "handle": handle, "field": field, "reason": reason,
               "retries": bumped["retries"], "max_retries": limit,
               "limit_reached": bumped["retries"] >= limit}
        if out["limit_reached"]:
            out.update(flag(conn, handle))
            out["team_notified"] = post_stuck(
                store.get_onboarding(conn, handle) or {}, field, raw)
        return out

    row = store.get_onboarding(conn, handle) or {}
    return {"ok": True, "handle": handle, "skipped": skipped,
            "tiktok": row.get("tiktok"), "email": row.get("email"), "phone": row.get("phone"),
            "still_needed": [] if row.get("tiktok") else ["tiktok"]}


# The collection order. `answer` walks this, so the agent never decides which question it
# is on — a decision it got wrong in QA by greeting and re-asking a question the welcome
# message had already asked and the creator had already answered.
FIELD_ORDER = ("tiktok", "email", "phone")
FIELD_PROMPTS = {
    "tiktok": "what's your TikTok username",
    "email": 'what\'s the best email to reach you — if you prefer not to share, just say "skip"',
    "phone": 'what\'s your WhatsApp or phone number — if you prefer not to share, just say "skip"',
}
RETRY_HINTS = {
    "not_a_handle": "ask for just the @name they post under, nothing else",
    "looks_like_email": "that's their email; you want the TikTok name",
    "not_an_email": "ask for an email address",
    "not_a_phone": "ask for a phone number with digits",
    "blank": "they sent nothing usable; ask again warmly",
    "required": "TikTok is the one thing you do need; say so kindly",
}


def skipped_fields(row: dict) -> list[str]:
    return [f for f in (row.get("skipped_fields") or "").split(",") if f]


def next_field(row: dict) -> str | None:
    """The field still outstanding, or None when everything has been asked."""
    declined = skipped_fields(row)
    for field in FIELD_ORDER:
        if not row.get(field) and field not in declined:
            return field
    return None


def answer(conn, handle: str, text: str, now: float | None = None) -> dict:
    """Take the creator's raw message and drive the whole collection flow one step.

    This is THE command for a creator's message. It works out which question is
    outstanding, validates their answer against it, records it (or counts a retry), and
    reports what to ask next — finishing onboarding outright once nothing is left.

    It exists because the agent kept getting the "which step am I on" decision wrong. On a
    thread's first turn the gateway prepends the whole skill document to the creator's
    message, so a one-word answer arrives buried under a procedure, and the model's
    instinct is to start the procedure rather than answer it. No amount of prompt wording
    beat that; removing the decision does.
    """
    row = store.get_onboarding(conn, handle)
    if row is None:
        start(conn, handle, now=now)
        row = store.get_onboarding(conn, handle) or {}

    field = next_field(row)
    if field is None:
        return _finish(conn, handle, now)

    result = set_fields(conn, handle, now=now, **{field: text})
    if not result["ok"]:
        result["ask"] = None if result.get("limit_reached") else field
        result["hint"] = RETRY_HINTS.get(result.get("reason"), "ask again warmly")
        result["question"] = FIELD_PROMPTS[field]
        return result

    if field in result.get("skipped", []):
        store.update_onboarding(
            conn, handle,
            skipped_fields=",".join(skipped_fields(row) + [field]),
        )
        result["declined"] = field

    row = store.get_onboarding(conn, handle) or {}
    upcoming = next_field(row)
    if upcoming is None:
        return {**result, **_finish(conn, handle, now)}
    return {**result, "ask": upcoming, "question": FIELD_PROMPTS[upcoming]}


def _finish(conn, handle: str, now: float | None) -> dict:
    """Everything asked — assign roles and hand the details to the team."""
    done = complete(conn, handle, now=now)
    return {**done, "ask": None,
            "next_step": "guidance" if done.get("ok") else "hand off to the team"}


def retry(conn, handle: str, ensure: Creator | None = None) -> dict:
    """Count a failed input attempt. Cumulative across fields — the limit is a total
    patience budget, not a per-field one."""
    row = store.get_onboarding(conn, handle)
    if row is None:
        if ensure is None:
            raise ValueError(f"unknown creator {handle!r}; run start first")
        store.upsert_creator(conn, ensure)
        row = store.get_onboarding(conn, handle) or {}
    count = int(row.get("retries") or 0) + 1
    store.update_onboarding(conn, handle, retries=count)
    return {"handle": handle, "retries": count}


def complete(conn, handle: str, role: str = "Creator", now: float | None = None,
             assign_roles: bool = True) -> dict:
    """Finish onboarding: grant the Discord roles, then hand the details to the team.

    Roles come FIRST and are the gate. With the access gate on they are the creator's key
    to the server, so "complete" while they are still locked out would be a lie — to the
    creator and to the team's signup log.
    """
    c = store.get_creator(conn, handle)
    if c is None:
        raise ValueError(f"unknown creator {handle!r}; run start first")
    if not c.tiktok:
        raise ValueError("cannot complete onboarding without a tiktok username")
    # email and phone are OPTIONAL — creators may say "skip" for either
    row = store.get_onboarding(conn, handle) or {}

    assigned: list[str] = []
    if assign_roles:
        import assign_role

        granted = assign_role.assign(row.get("discord_id") or "")
        if not granted["ok"]:
            store.mark_active(conn, handle, ts=now)
            return {"ok": False, "handle": handle, "state": c.onboarding_state,
                    "needs_team": True, "error": granted["error"],
                    "team_notified": post_role_failure(row, granted["error"])}
        assigned = granted.get("assigned") or []

    c.role = role
    c.onboarding_state = COMPLETE
    store.upsert_creator(conn, c)
    store.mark_active(conn, handle, ts=now)
    row = store.get_onboarding(conn, handle) or {}
    # Hand the captured details to the team the moment they're captured. Both sinks are
    # deterministic and best-effort: neither can block or fail a creator's onboarding.
    from _lib import sheet

    return {
        "ok": True,
        "handle": handle, "state": COMPLETE, "role": role, "assigned": assigned,
        "posted_to_slack": post_signup(row),                 # #ace-onboarding
        "sheet_synced": sheet.sync_creator(row),             # no-op without a webhook
    }


def format_signup(row: dict) -> str:
    """The team-facing new-creator card. Optional fields say so explicitly rather than
    showing a blank, so nobody wonders whether it failed to capture."""
    def shown(value: str | None) -> str:
        return value if value else "_not shared_"

    joined = row.get("joined_at")
    when = ""
    if joined:
        from datetime import datetime, timezone

        when = datetime.fromtimestamp(float(joined), tz=timezone.utc).strftime("%b %-d, %Y")
    lines = [
        f"✅ *New creator onboarded:* {row.get('handle') or '(unknown)'}",
        f"• TikTok: *{shown(row.get('tiktok'))}*",
        f"• Email: {shown(row.get('email'))}",
        f"• WhatsApp/phone: {shown(row.get('phone'))}",
    ]
    if row.get("discord_id"):
        lines.append(f"• Discord: <https://discord.com/users/{row['discord_id']}|profile>")
    if when:
        lines.append(f"• Joined: {when}")
    return "\n".join(lines)


def post_signup(row: dict) -> bool:
    """Post the new-creator card to the brand's onboarding Slack channel."""
    return _post(format_signup(row), key="data_channel", default=DATA_CHANNEL)


def post_role_failure(row: dict, error: str) -> bool:
    """A creator finished the questions but could not be let in. This is the loudest
    failure in the whole flow — with the access gate on they are standing at a locked
    door — so it goes to the escalation channel, not the signup log."""
    handle = row.get("handle") or "(unknown)"
    lines = [
        f"🚨 *Onboarding blocked — role assignment failed for {handle}*",
        f"• Reason: {error}",
        f"• TikTok: {row.get('tiktok') or '_not shared_'}",
    ]
    if row.get("discord_id"):
        lines.append(f"• Discord: <https://discord.com/users/{row['discord_id']}|profile>")
    lines.append("• They answered everything and are waiting — grant their roles by hand, "
                 "then run `onboarding.py complete` to log the signup.")
    return _post("\n".join(lines), key="slack_channel")


def post_stuck(row: dict, field: str, last_answer: str) -> bool:
    """Patience budget spent on one field. A human takes it from here."""
    handle = row.get("handle") or "(unknown)"
    lines = [
        f"⚠️ *Onboarding stuck — {handle} can't get past “{field}”*",
        f"• Last answer: “{(last_answer or '').strip()[:120]}”",
        f"• Attempts: {row.get('retries')}",
    ]
    if row.get("thread_id"):
        lines.append(f"• Thread: <https://discord.com/channels/@me/{row['thread_id']}|open>")
    lines.append("• Ace has stopped asking and told them the team will help.")
    return _post("\n".join(lines), key="slack_channel")


def _post(text: str, key: str, default: str | None = None) -> bool:
    """Send one brand-tagged Slack message.

    ``key`` selects the channel from ``ace.onboarding``; with no override and no
    ``default``, slack_cli falls back to the brand's ``ace.slack_channel`` (the shared
    #ace-escalations). Best-effort by contract: every caller is on a creator's critical
    path, so Slack being down must never break onboarding.
    """
    from _lib import sheet, slack_cli

    ace = sheet.brand_config()
    channel = (ace.get("onboarding") or {}).get(key) or default
    argv = ["post", "--text", text] + (["--channel", channel] if channel else [])
    try:
        return slack_cli.main(argv) == 0
    except Exception:  # noqa: BLE001 - see docstring
        return False


def guided(conn, handle: str, now: float | None = None) -> dict:
    """Guidance sequence delivered — the nudge clock starts here."""
    if store.get_onboarding(conn, handle) is None:
        raise ValueError(f"unknown creator {handle!r}; run start first")
    ts = now if now is not None else time.time()
    store.update_onboarding(conn, handle, onboarding_state="guided", guided_at=str(ts),
                            last_active_at=None)
    return {"handle": handle, "state": "guided"}


def flag(conn, handle: str) -> dict:
    """Stop looping on bad input / blocked step; a human takes over from here."""
    store.update_onboarding(conn, handle, onboarding_state="flagged")
    return {"handle": handle, "state": "flagged"}


def status(conn, handle: str) -> dict:
    row = store.get_onboarding(conn, handle)
    if row is None:
        return {"handle": handle, "state": None, "error": "not found"}
    out = {k: row.get(k) for k in (
        "handle", "onboarding_state", "tiktok", "email", "phone", "role", "retries",
        "joined_at", "guided_at", "nudged_at", "escalated_at", "resolved_at",
        "last_active_at", "thread_id",
    )}
    out["declined"] = skipped_fields(row)
    out["ask"] = next_field(row)
    return out


def reset(conn, handle: str, now: float | None = None) -> dict:
    """Back to the start of the flow (redo / rejoined). Sets state to 'new': the next
    onboarding tick re-onboards them from scratch — fresh private thread (the old one is
    archived; a rejoiner lost access to it anyway when they left) + fresh welcome."""
    if store.get_onboarding(conn, handle) is None:
        raise ValueError(f"unknown creator {handle!r}")
    store.update_onboarding(
        conn, handle, onboarding_state=NEW, tiktok=None, email=None, role=None,
        retries=0, guided_at=None, nudged_at=None, escalated_at=None,
        escalation_channel=None, escalation_ts=None, resolved_at=None, last_active_at=None,
        joined_at=str(now if now is not None else time.time()),
    )
    return {"handle": handle, "state": NEW, "reset": True,
            "next": "the onboarding tick re-onboards them with a fresh thread within ~2 min"}


def resolve(conn, handle: str, now: float | None = None) -> dict:
    """Team closes an escalated case by hand (the ✅ Slack reaction does this automatically)."""
    store.update_onboarding(conn, handle, onboarding_state="resolved",
                            resolved_at=str(now if now is not None else time.time()))
    return {"handle": handle, "state": "resolved"}


def set_test_mode(profile_dir: Path, on: bool) -> dict:
    """Flip ace.onboarding.test_mode in the profile config (compressed timers for QA)."""
    import yaml

    cfg_path = profile_dir / "config.yaml"
    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    ob = config.setdefault("ace", {}).setdefault("onboarding", {})
    ob["test_mode"] = on
    cfg_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return {"test_mode": on, "config": str(cfg_path)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Creator onboarding state + team controls.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "answer", "set", "retry", "complete", "guided", "flag", "status",
                 "reset", "resolve"):
        p = sub.add_parser(name)
        p.add_argument("--handle", required=True)
        if name == "answer":
            p.add_argument("--text", required=True, help="the creator's message, verbatim")
        if name == "set":
            p.add_argument("--tiktok")
            p.add_argument("--email")
            p.add_argument("--phone")
        if name == "complete":
            p.add_argument("--role", default="Creator")
    tm = sub.add_parser("test-mode")
    tm.add_argument("state", choices=["on", "off"])
    tm.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "."))
    sub.add_parser("stats")
    args = ap.parse_args(argv)

    if args.cmd == "test-mode":
        print(json.dumps(set_test_mode(Path(args.profile_dir), args.state == "on")))
        return 0

    conn = store.connect()
    handlers = {
        "start": lambda: start(conn, args.handle),
        "answer": lambda: answer(conn, args.handle, args.text),
        "set": lambda: set_fields(conn, args.handle, args.tiktok, args.email, args.phone),
        "retry": lambda: retry(conn, args.handle),
        "complete": lambda: complete(conn, args.handle, args.role),
        "guided": lambda: guided(conn, args.handle),
        "flag": lambda: flag(conn, args.handle),
        "status": lambda: status(conn, args.handle),
        "reset": lambda: reset(conn, args.handle),
        "resolve": lambda: resolve(conn, args.handle),
        "stats": lambda: store.onboarding_stats(conn),
    }
    print(json.dumps(handlers[args.cmd]()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
