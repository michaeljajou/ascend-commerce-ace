#!/usr/bin/env python3
"""Configure a brand inside its (already-created) Hermes profile.

Pure builders (validated + unit-tested) turn a brand spec into the per-profile artifacts:
  - config.yaml      Discord channel scoping + model/provider + brand ids   (JSON content; JSON is valid YAML)
  - SOUL.md          brand voice + the locked behavioral rules
  - cronjobs.yaml    the recurring jobs with this brand's channel targets    (JSON content)

The profile must already exist (a Hermes-CLI step attaches the bot/Slack tokens). This skill
does NOT create the profile. After writing config, the skill triggers the first KB ingest.

NOTE: config/cron are emitted as JSON (which is valid YAML) so they're round-trippable in tests
without a YAML dependency. Phase 0 spike confirms whether Hermes prefers files or `hermes config set`.

Usage:
    python setup.py --spec brand.json [--profile-dir <dir>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # → skills

# Channel behaviors from the spec's channel map.
BEHAVIORS = {
    "POST_ONLY",      # announcements: cron posts, no replies
    "POST_ANSWER",    # campaigns/challenges/team-war: cron posts + answers logistics
    "ANSWER",         # our-products: answers from KB
    "FULL_ACTIVE",    # community-chat: primary Q&A + sentiment
    "MONITOR_ONLY",   # success-stories: read sentiment, never reply publicly
    "PAID_COLLAB",    # private 1:1 collab channels
    "AMBASSADOR",     # ambassador group channel
    "INACTIVE",       # content-inspo, coaching, coaching-calls
}

# Behaviors where Ace answers messages without needing a mention.
_FREE_RESPONSE = {"FULL_ACTIVE", "ANSWER", "POST_ANSWER", "PAID_COLLAB", "AMBASSADOR"}
# Behaviors where Ace must not converse (replies suppressed entirely).
_IGNORED = {"INACTIVE", "POST_ONLY"}
# Behaviors where cron posts content.
_POST_TARGET = {"POST_ONLY", "POST_ANSWER"}

REQUIRED_KEYS = ("brand_id", "discord", "slack_channel", "drive_folder", "model")

DEFAULTS = {
    "classify_model": "anthropic/claude-haiku-4-5",
    "embed_model": "openai/text-embedding-3-small",
    "voice": "Friendly, concise, and encouraging — hype but professional.",
}


def validate_spec(spec: dict) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in spec]
    if missing:
        raise ValueError(f"brand spec missing required keys: {missing}")
    discord = spec["discord"]
    if "guild_id" not in discord or "channels" not in discord:
        raise ValueError("discord must include 'guild_id' and 'channels'")
    bad = {ch: b for ch, b in discord["channels"].items() if b not in BEHAVIORS}
    if bad:
        raise ValueError(f"invalid channel behaviors: {bad}; allowed: {sorted(BEHAVIORS)}")


def channel_scoping(channels: dict[str, str]) -> dict[str, list[str]]:
    """Translate the channel→behavior map into Hermes scoping lists.

    `monitor` is kept separate (not free-response, not ignored): success-stories must be *read*
    for sentiment but never replied to publicly — the `monitor-channel` skill handles that.
    The exact Hermes wiring for read-only monitoring is a Phase 0 spike item.
    """
    out = {"free_response": [], "ignored": [], "monitor": [], "post_targets": []}
    for ch, behavior in channels.items():
        if behavior == "MONITOR_ONLY":
            out["monitor"].append(ch)
        elif behavior in _FREE_RESPONSE:
            out["free_response"].append(ch)
        elif behavior in _IGNORED:
            out["ignored"].append(ch)
        if behavior in _POST_TARGET:
            out["post_targets"].append(ch)
    return {k: sorted(v) for k, v in out.items()}


def build_config(spec: dict) -> dict:
    d = {**DEFAULTS, **spec}
    return {
        "brand_id": d["brand_id"],
        "model": {"provider": "openrouter", "default": d["model"], "classify": d["classify_model"]},
        "embed_model": d["embed_model"],
        "discord": {
            "guild_id": str(d["discord"]["guild_id"]),
            "channels": d["discord"]["channels"],
            "scoping": channel_scoping(d["discord"]["channels"]),
        },
        "slack_channel": d["slack_channel"],
        "drive_folder": d["drive_folder"],
        "growi_project": d.get("growi_project"),
    }


def render_soul(spec: dict, template_path: Path | None = None) -> str:
    d = {**DEFAULTS, **spec}
    template_path = template_path or (Path(__file__).resolve().parents[1] / "templates" / "SOUL.md.tmpl")
    tmpl = template_path.read_text(encoding="utf-8")
    summary = "\n".join(
        f"- #{ch}: {behavior}" for ch, behavior in sorted(d["discord"]["channels"].items())
    )
    return tmpl.format(
        brand_name=d.get("brand_name", d["brand_id"]),
        voice=d["voice"],
        channel_summary=summary,
        slack_channel=d["slack_channel"],
    )


def build_cronjobs(spec: dict) -> list[dict]:
    """Recurring jobs with this brand's channel targets (activated from skill blueprints)."""
    scoping = channel_scoping(spec["discord"]["channels"])
    post_target = scoping["post_targets"][0] if scoping["post_targets"] else None
    jobs = [
        {"name": "ingest-knowledge", "schedule": "0 4 * * *", "skill": "ingest-knowledge", "deliver": None},
        {"name": "daily-digest", "schedule": "0 9 * * *", "skill": "daily-digest",
         "deliver": "slack"},
        {"name": "nudge-inactive", "schedule": "0 10 * * *", "skill": "nudge-inactive", "deliver": None},
    ]
    if post_target:
        jobs.append(
            {"name": "weekly-reminders", "schedule": "0 16 * * 1,4", "skill": "weekly-reminders",
             "deliver": f"discord:#{post_target}"}
        )
    return jobs


def write_profile(spec: dict, profile_dir: str | Path) -> dict:
    validate_spec(spec)
    profile = Path(profile_dir)
    profile.mkdir(parents=True, exist_ok=True)
    config_path = profile / "config.yaml"
    soul_path = profile / "SOUL.md"
    cron_path = profile / "cronjobs.yaml"
    # JSON content is valid YAML — keeps this dependency-free + round-trippable in tests.
    config_path.write_text(json.dumps(build_config(spec), indent=2), encoding="utf-8")
    cron_path.write_text(json.dumps(build_cronjobs(spec), indent=2), encoding="utf-8")
    soul_path.write_text(render_soul(spec), encoding="utf-8")
    return {"config": str(config_path), "soul": str(soul_path), "cronjobs": str(cron_path)}


def _load_spec(arg: str) -> dict:
    p = Path(arg)
    return json.loads(p.read_text(encoding="utf-8") if p.exists() else arg)


def main(argv: list[str] | None = None) -> int:
    import os

    ap = argparse.ArgumentParser(description="Configure a brand inside its Hermes profile.")
    ap.add_argument("--spec", required=True, help="path to a brand spec JSON file (or inline JSON)")
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_PROFILE_DIR", "./profile"))
    args = ap.parse_args(argv)

    spec = _load_spec(args.spec)
    written = write_profile(spec, args.profile_dir)
    print(json.dumps({"written": written, "next": "run ingest-knowledge for the first KB load"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
