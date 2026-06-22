#!/usr/bin/env python3
"""Build a results/winner announcement from Growi data (Announcement Type 3).

`render` is pure (testable from a fixture payload). `main` fetches live from Growi then renders.
Posting to Discord + #success-stories is done by the skill via Hermes delivery.

Usage:
    python results.py --base-url https://growi... --project <proj>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

from _lib import growi  # noqa: E402


def render(results: "growi.CampaignResults") -> str:
    lines = [f"🏆 *{results.campaign} — Results!*", ""]
    if results.winners:
        lines.append("*Winners:*")
        for w in results.winners:
            prize = f" — {w['prize']}" if w.get("prize") else ""
            metric = f" ({w['metric']})" if w.get("metric") else ""
            lines.append(f"  • {w.get('handle', 'unknown')}{prize}{metric}")
    if results.top_performers:
        tops = ", ".join(t.get("handle", "?") for t in results.top_performers[:5])
        lines.append(f"*Top performers:* {tops}")
    if results.stats:
        stat_str = ", ".join(f"{k}: {v}" for k, v in results.stats.items())
        lines.append(f"*Stats:* {stat_str}")
    lines.append("\nHuge thanks to everyone who participated! 🎉")
    return "\n".join(lines)


def render_payload(payload: dict) -> str:
    return render(growi.parse_results(payload))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a Growi results announcement.")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--project", required=True)
    args = ap.parse_args(argv)

    results = growi.fetch_results(args.base_url, args.project)
    print(json.dumps({"text": render(results)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
