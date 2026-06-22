#!/usr/bin/env python3
"""Shared logging CLI used by instruction-only skills to record outcomes in the profile store.

This keeps `answer-from-kb`, `escalate-to-team`, and `record-feedback` instruction-driven: they
just invoke this tiny shared utility instead of each carrying logging logic.

Usage:
    python log_cli.py interaction --status answered  --channel community-chat \
        --handle @creator --question "..." --answer "..."        # prints the interaction id
    python log_cli.py feedback --interaction-id 42 --value up
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # → skills

from _lib import store  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record interactions/feedback in the profile store.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("interaction")
    i.add_argument("--status", required=True, choices=["answered", "escalated", "routed"])
    i.add_argument("--channel")
    i.add_argument("--handle")
    i.add_argument("--question")
    i.add_argument("--answer")

    f = sub.add_parser("feedback")
    f.add_argument("--interaction-id", type=int, required=True)
    f.add_argument("--value", required=True, choices=["up", "down"])

    args = ap.parse_args(argv)
    conn = store.connect()

    if args.cmd == "interaction":
        iid = store.log_interaction(
            conn,
            status=args.status,
            channel=args.channel,
            creator_handle=args.handle,
            question=args.question,
            answer=args.answer,
        )
        print(json.dumps({"interaction_id": iid}))
    else:
        store.log_feedback(conn, args.interaction_id, args.value)
        print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
