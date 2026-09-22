#!/usr/bin/env python3
"""Post the weekly reminder into the brand's announcement channel (deterministic delivery).

Why a script and not Hermes' cron delivery: Hermes has ONE delivery target per job and
always delivers a failed run's error summary to it. While weekly-reminders delivered
straight into #announcements, the 2026-09-21 run's `HTTP 402` notice landed in front of
QBounce's and Prime Natural's creators. The job now delivers to the private home channel
(#agent-ace) and this script puts the reminder where creators read it; the agent ends with
[SILENT], so a good run delivers nothing at all and a failure is only ever seen by the team.

Target: the brand's first POST_ONLY/POST_ANSWER channel from ace/brand.json (announcements
on every brand so far), resolved to its id through channel_directory.json. The agent never
chooses the channel. No mention of any kind is expanded — a reminder pings nobody.

Hand the text over on STDIN inside a quoted heredoc — never through --text "..." in a
shell (bash keeps `\\n` as two characters and expands `$50` to `0` inside double quotes;
see sweep-unanswered/scripts/reply.py for the incidents).

Usage:
    python3 post.py --stdin <<'EOF'
    🔥 **September campaign — halfway there!** ...
    EOF
    python3 post.py --dry-run --text x               # resolve the target, post nothing
    python3 post.py --channel-id <id> --stdin        # explicit target (operator tests)

Exit codes: 0 posted (or dry run); 1 error; 2 refused — this bot already posted in the
channel within the last hour (an agent retry must not double-post; --force overrides).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills, for _lib
from _lib import brand  # noqa: E402
from _lib.discord import (  # noqa: E402
    DISCORD_MAX_CONTENT, bot_token, channel_ids, post_message, recent_own_post,
)

GUARD_MINUTES = 60


def clean_text(text: str) -> str:
    """Repair what a shell did to the text: a literal backslash-n is the newline the
    agent meant."""
    return text.replace("\\r\\n", "\n").replace("\\n", "\n").strip()


def resolve_target(profile: Path, channel_id: str | None) -> tuple[str | None, str]:
    """(channel name, channel id). An explicit id wins; otherwise the brand's post channel."""
    if channel_id:
        return None, channel_id
    name = brand.post_channel(brand.config(profile))
    if not name:
        raise LookupError(
            "ace/brand.json has no POST_ONLY/POST_ANSWER channel to post reminders to — "
            "pass --channel-id or fix the brand spec."
        )
    found, missing = channel_ids(profile, [name])          # FileNotFoundError before first connect
    if missing:
        raise LookupError(f"channel #{name} is not in channel_directory.json — create it on the "
                          "server (or fix the spec) and restart the gateway.")
    return name, found[name]


def _err(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile-dir", help="Hermes profile root (default: from ACE_DATA_DIR/HERMES_HOME)")
    ap.add_argument("--channel-id", help="post here instead of the brand's POST_* channel")
    ap.add_argument("--text", help="reminder text (prefer --stdin with a quoted heredoc)")
    ap.add_argument("--stdin", action="store_true", help="read the reminder text from stdin")
    ap.add_argument("--force", action="store_true", help="post even if this bot posted here within the hour")
    ap.add_argument("--dry-run", action="store_true", help="resolve and check everything, post nothing")
    args = ap.parse_args(argv)
    profile = Path(args.profile_dir) if args.profile_dir else brand.profile_dir()

    text = clean_text(sys.stdin.read() if args.stdin else (args.text or ""))
    if not text:
        _err("empty reminder text.")
        return 1
    if len(text) > DISCORD_MAX_CONTENT:
        _err(f"reminder is {len(text)} characters; Discord allows {DISCORD_MAX_CONTENT}. Shorten it.")
        return 1

    try:
        channel_name, channel_id = resolve_target(profile, args.channel_id)
    except (LookupError, FileNotFoundError) as exc:
        _err(str(exc))
        return 1
    token = bot_token(profile)
    if not token:
        _err("DISCORD_BOT_TOKEN not set and not found in the profile .env.")
        return 1

    recent = recent_own_post(token, channel_id, within_minutes=GUARD_MINUTES)
    if recent and not args.force:
        _err(f"refusing to post: this bot already posted message {recent.get('id')} in channel "
             f"{channel_id} at {recent.get('timestamp')}, within the last {GUARD_MINUTES} minutes. "
             "If that was not this reminder, re-run with --force.")
        return 2
    if args.dry_run:
        print(json.dumps({"dry_run": True, "channel": channel_name, "channel_id": channel_id,
                          "characters": len(text)}))
        return 0

    try:
        sent = post_message(token, channel_id, text)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        _err(f"Discord rejected the post ({exc.code}): {body}")
        return 1
    print(json.dumps({"posted": sent.get("id"), "channel": channel_name, "channel_id": channel_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
