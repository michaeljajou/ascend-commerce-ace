"""Structured logging for every Ace script invocation — the debugging record.

Why this exists: diagnosing an onboarding failure used to mean correlating four separate
sources by hand — Hermes' `agent.log` (timings only, no arguments), the `state.db` messages
table (the agent's tool calls), the Ace store (resulting state), and the Discord API (what
the creator actually saw). Every QA round cost a fresh ad-hoc script, and the bugs it kept
turning up were exactly the things none of those sources showed on their own:

  * a script dying on `import yaml` because the agent's sandbox interpreter differs from
    the one every server-side check used
  * the agent passing ``--text ""`` — dropping the creator's message entirely
  * one creator message costing six tool calls while the agent tried to pip-install its way
    out of a crash

So each run of an Ace script appends ONE json line here: what was asked, what came back,
how long it took, which interpreter ran it, and the traceback if it failed. Read it with
``onboarding.py trace --handle @x``.

Contract: logging NEVER raises and never changes behaviour. A creator's onboarding must not
fail because a log file is unwritable — every call is wrapped, and a failure to log is
silent by design.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

LOG_FILENAME = "ace-trace.jsonl"
# Past this the file is rotated to <name>.1 (one generation kept). Big enough to hold a
# busy brand's history, small enough to stay greppable and never fill a small VPS disk.
MAX_BYTES = 5 * 1024 * 1024


def log_path() -> Path:
    from . import store

    return store.data_dir() / LOG_FILENAME


def _rotate(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size > MAX_BYTES:
            path.replace(path.with_suffix(path.suffix + ".1"))
    except OSError:
        pass


def record(event: str, **fields) -> None:
    """Append one structured event. Silent on any failure — see the module docstring."""
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": event,
            # The interpreter is here because a mismatch between it and the one used for
            # verification hid a whole class of failure for three QA rounds.
            "python": sys.executable,
            "pid": os.getpid(),
            **fields,
        }
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")
    except Exception:  # noqa: BLE001 - logging must never break a creator's onboarding
        pass


def read(handle: str | None = None, limit: int = 200) -> list[dict]:
    """Recent events, oldest first, optionally for one creator."""
    path = log_path()
    entries: list[dict] = []
    for source in (path.with_suffix(path.suffix + ".1"), path):
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if handle is None or entry.get("handle") == handle:
                entries.append(entry)
    return entries[-limit:]


class Invocation:
    """Context manager timing one CLI run and recording its outcome either way.

        with trace.Invocation("onboarding.answer", handle="@ava", args={...}) as run:
            run.result = do_the_work()
    """

    def __init__(self, command: str, **fields):
        self.command = command
        self.fields = fields
        self.result = None
        self._started = 0.0

    def __enter__(self) -> "Invocation":
        self._started = time.time()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed = round(time.time() - self._started, 3)
        if exc is not None:
            record("script.error", command=self.command, duration_s=elapsed,
                   error=f"{exc_type.__name__}: {exc}",
                   traceback="".join(traceback.format_exception(exc_type, exc, tb))[-2000:],
                   **self.fields)
        else:
            record("script.ok", command=self.command, duration_s=elapsed,
                   result=self.result, **self.fields)
        return False        # never swallow the exception


def render(entries: list[dict]) -> str:
    """Human-readable timeline — what to paste when reporting a bad onboarding."""
    if not entries:
        return ("No trace events recorded. Either nothing has run yet, or the scripts ran "
                "against a different ACE_DATA_DIR than this one "
                f"({log_path().parent}).")
    lines = []
    for e in entries:
        stamp = str(e.get("ts", ""))[11:23]
        head = f"{stamp}  {e.get('event', '?'):<13} {e.get('command', '')}"
        if (d := e.get("duration_s")) is not None:
            head += f"  ({d}s)"
        lines.append(head)
        if args := e.get("args"):
            lines.append(f"              args: {json.dumps(args, default=str)[:400]}")
        if e.get("event") == "script.error":
            lines.append(f"              ERROR: {e.get('error')}")
            for tb_line in str(e.get("traceback", "")).strip().splitlines()[-4:]:
                lines.append(f"                {tb_line}")
        elif (result := e.get("result")) is not None:
            lines.append(f"              -> {json.dumps(result, default=str)[:400]}")
        if (py := e.get("python")) and "hermes" not in str(py):
            lines.append(f"              python: {py}")
    return "\n".join(lines)
