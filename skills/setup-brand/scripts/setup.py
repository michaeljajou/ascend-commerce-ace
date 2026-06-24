#!/usr/bin/env python3
"""Configure a brand inside its (already-created) Hermes profile.

Pure builders (validated + unit-tested) turn a brand spec into the per-profile artifacts:
  - config.yaml  (MERGED)  Ace brand config under the `ace:` key — never clobbers Hermes' own keys
                           (model, skills.external_dirs, …). Answer model set at top-level `model:`
                           only when specified; otherwise the brand inherits Hermes' default.
  - SOUL.md                brand voice + the locked behavioral rules
  - cronjobs.yaml          the recurring jobs with this brand's channel targets (separate file)
  - .env  (merged)         ACE_DATA_DIR=<profile>/ace — the data-dir contract store.py/knowledge.py read

This is the Hermes **adapter**: the bundle's core stays orchestrator-agnostic (it reads only
``ACE_DATA_DIR``), and this skill is the one place that knows Hermes — it derives the profile's data
path and writes ``ACE_DATA_DIR`` into the profile ``.env``. Porting to another orchestrator means a
different setup adapter, not changes to store.py or any behavior skill.

The profile must already exist (a Hermes-CLI step attaches the bot/Slack tokens). This skill
does NOT create the profile. Brand knowledge is a YAML file the team maintains in the profile (read
live by get-knowledge) — there is no ingest/embedding step.

Usage:
    python setup.py --spec brand.json [--profile-dir <dir>]
"""

from __future__ import annotations

import argparse
import json
import os
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

# model + slack_channel are OPTIONAL: no model → inherit Hermes' default; no slack → default channel.
REQUIRED_KEYS = ("brand_id", "discord")

DEFAULTS = {
    "classify_model": "anthropic/claude-haiku-4-5",
    "voice": "Friendly, concise, and encouraging — hype but professional.",
}


def _default_slack() -> str | None:
    """The fallback escalation channel when a brand spec omits one.

    Resolution (first found):
      1. ``ACE_DEFAULT_SLACK_CHANNEL`` env (handy from the shell)
      2. the root deployment config: ``$HERMES_HOME/config.yaml`` → ``ace.default_slack_channel``
         (robust in the agent sandbox, where custom env vars are stripped but HERMES_HOME is passed)
    """
    if env := os.environ.get("ACE_DEFAULT_SLACK_CHANNEL"):
        return env
    home = os.environ.get("HERMES_HOME")
    if home:
        cfg = Path(home) / "config.yaml"
        if cfg.exists():
            try:
                import yaml

                data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                return (data.get("ace") or {}).get("default_slack_channel")
            except Exception:
                return None
    return None


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
    """The Ace brand-config block (stored under the `ace:` key). The answer model is NOT here —
    it's set at Hermes' top-level `model:` only when specified (see _merge_config)."""
    d = {**DEFAULTS, **spec}
    cfg = {
        "brand_id": d["brand_id"],
        "discord": {
            "guild_id": str(d["discord"]["guild_id"]),
            "channels": d["discord"]["channels"],
            "scoping": channel_scoping(d["discord"]["channels"]),
        },
        "classify_model": d["classify_model"],
        "knowledge_file": "knowledge.yaml",  # the brand knowledge the team maintains in this profile
    }
    slack = spec.get("slack_channel") or _default_slack()
    if slack:
        cfg["slack_channel"] = slack
    if d.get("growi_project"):
        cfg["growi_project"] = d["growi_project"]
    return cfg


def render_soul(spec: dict, template_path: Path | None = None) -> str:
    d = {**DEFAULTS, **spec}
    template_path = template_path or (Path(__file__).resolve().parents[1] / "templates" / "SOUL.md.tmpl")
    tmpl = template_path.read_text(encoding="utf-8")
    summary = "\n".join(
        f"- #{ch}: {behavior}" for ch, behavior in sorted(d["discord"]["channels"].items())
    )
    slack = spec.get("slack_channel") or _default_slack() or "the team's Slack channel"
    return tmpl.format(
        brand_name=d.get("brand_name", d["brand_id"]),
        voice=d["voice"],
        channel_summary=summary,
        slack_channel=slack,
    )


def build_cronjobs(spec: dict) -> list[dict]:
    """Recurring jobs with this brand's channel targets (activated from skill blueprints)."""
    scoping = channel_scoping(spec["discord"]["channels"])
    post_target = scoping["post_targets"][0] if scoping["post_targets"] else None
    jobs = [
        {"name": "daily-digest", "schedule": "0 9 * * *", "skill": "daily-digest", "deliver": "slack"},
        {"name": "nudge-inactive", "schedule": "0 10 * * *", "skill": "nudge-inactive", "deliver": None},
    ]
    if post_target:
        jobs.append(
            {"name": "weekly-reminders", "schedule": "0 16 * * 1,4", "skill": "weekly-reminders",
             "deliver": f"discord:#{post_target}"}
        )
    return jobs


def ensure_env(profile_dir: str | Path, updates: dict[str, str]) -> str:
    """Idempotently set KEY=VALUE lines in the profile's .env, preserving existing entries (tokens)."""
    env_path = Path(profile_dir) / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    index = {}
    for i, line in enumerate(lines):
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            index[s.split("=", 1)[0].strip()] = i
    for key, value in updates.items():
        new_line = f"{key}={value}"
        if key in index:
            lines[index[key]] = new_line
        else:
            lines.append(new_line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(env_path)


def merge_config(config_path: str | Path, spec: dict) -> None:
    """Merge Ace's brand config into the profile config.yaml WITHOUT clobbering Hermes' own keys
    (model, skills.external_dirs, …). Ace metadata goes under `ace:`; the answer model is set at
    Hermes' top-level `model:` only when the spec specifies one (else the brand inherits the default).
    """
    import yaml  # PyYAML is a declared dep; needed to preserve existing Hermes config

    path = Path(config_path)
    existing = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    existing = existing or {}
    existing["ace"] = build_config(spec)
    if spec.get("model"):
        existing["model"] = spec["model"]  # Hermes reads top-level model; omit → inherit default
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")


def write_profile(spec: dict, profile_dir: str | Path) -> dict:
    validate_spec(spec)
    profile = Path(profile_dir)
    profile.mkdir(parents=True, exist_ok=True)
    config_path = profile / "config.yaml"
    soul_path = profile / "SOUL.md"
    cron_path = profile / "cronjobs.yaml"
    merge_config(config_path, spec)  # MERGE under `ace:` — preserves Hermes keys + external_dirs
    cron_path.write_text(json.dumps(build_cronjobs(spec), indent=2), encoding="utf-8")
    soul_path.write_text(render_soul(spec), encoding="utf-8")
    # The agnostic seam: point the core at this profile's data dir via ACE_DATA_DIR (merged, not clobbered).
    data_dir = (profile / "ace").resolve()
    env_path = ensure_env(profile, {"ACE_DATA_DIR": str(data_dir)})
    return {
        "config": str(config_path),
        "soul": str(soul_path),
        "cronjobs": str(cron_path),
        "env": env_path,
        "data_dir": str(data_dir),
    }


def _load_spec(arg: str) -> dict:
    p = Path(arg)
    return json.loads(p.read_text(encoding="utf-8") if p.exists() else arg)


def main(argv: list[str] | None = None) -> int:
    import os

    ap = argparse.ArgumentParser(description="Configure a brand inside its Hermes profile.")
    ap.add_argument("--spec", required=True, help="path to a brand spec JSON file (or inline JSON)")
    # When a profile runs, Hermes sets HERMES_HOME to that profile's dir — the right default here.
    ap.add_argument("--profile-dir", default=os.environ.get("HERMES_HOME", "./profile"))
    args = ap.parse_args(argv)

    spec = _load_spec(args.spec)
    written = write_profile(spec, args.profile_dir)
    print(json.dumps({
        "written": written,
        "next": f"place knowledge.yaml in {written['data_dir']} (ACE_DATA_DIR); validate with get-knowledge",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
