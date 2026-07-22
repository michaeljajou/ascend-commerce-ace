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
    # Every brand server gets an ops channel for Ace's proactive output (cron results,
    # notifications). resolve_channels.py resolves this NAME to an ID post-connect and
    # writes DISCORD_HOME_CHANNEL into the profile .env. Override per brand with
    # spec discord.home_channel.
    "home_channel": "agent-ace",
    # The Ascend team holds this role in every brand server. Role-holders are never
    # swept (their posts get no reply), and their reply within the grace window
    # releases Ace. Override per brand with spec discord.team_role.
    "team_role": "Ascend Team",
}

# SOUL.md managed block: resolve_channels.py writes the live channel-name → <#id> map
# between these markers post-connect; write_profile preserves the block when it
# regenerates SOUL.md from the template on a setup re-run.
CHANNEL_DIR_START = "<!-- ace:channel-directory:start -->"
CHANNEL_DIR_END = "<!-- ace:channel-directory:end -->"


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
        "brand_name": d.get("brand_name", d["brand_id"]),  # scripts stamp this on Slack posts
        "discord": {
            "guild_id": str(d["discord"]["guild_id"]),
            "channels": d["discord"]["channels"],
            "scoping": channel_scoping(d["discord"]["channels"]),
            # Resolved to DISCORD_HOME_CHANNEL(_NAME) in .env by resolve_channels.py.
            "home_channel": str(d["discord"].get("home_channel") or d["home_channel"]),
            # Reply gating: the team gets first right of reply; the ace-sweep.py cron
            # script (zero-token) wakes the agent only for creator messages the team
            # hasn't answered within sweep_minutes. team_role marks who "the team" is.
            "sweep_minutes": int(d["discord"].get("sweep_minutes", 5)),
            "team_role": str(d["discord"].get("team_role") or d["team_role"]),
        },
        "classify_model": d["classify_model"],
        "knowledge_file": "knowledge.yaml",  # the brand knowledge the team maintains in this profile
    }
    # All brands share one escalation channel by default; slack_cli.py brand-tags
    # every post so the team can tell brands apart.
    cfg["slack_channel"] = spec.get("slack_channel") or _default_slack() or "#ace-escalations"
    cfg["onboarding"] = build_onboarding(spec)
    if d.get("growi_project"):
        cfg["growi_project"] = d["growi_project"]
    return cfg


def build_onboarding(spec: dict) -> dict:
    """The ace.onboarding block (Vaulty replacement). Inert until the operator flips
    `enabled` — the tick script, thread creation, and timers all gate on it."""
    d = {**DEFAULTS, **spec}
    ob = spec.get("onboarding") or {}
    block = {
        "enabled": bool(ob.get("enabled", False)),
        # who can see/manage the private onboarding threads (defaults to the team role)
        "staff_role": str(ob.get("staff_role") or spec.get("discord", {}).get("team_role")
                          or d["team_role"]),
        # Vaulty parity: completion assigns BOTH roles (name match is case-insensitive)
        "creator_roles": ob.get("creator_roles") or ["onboarded", "creator"],
        "nudge_hours": ob.get("nudge_hours", 48),
        "escalate_days": ob.get("escalate_days", 7),
        "nudge_via": ob.get("nudge_via", "dm"),          # dm | space (their onboarding thread)
        "max_retries": ob.get("max_retries", 3),
        "archive_days": ob.get("archive_days", 7),
        "test_mode": bool(ob.get("test_mode", False)),   # compressed timers for QA
        "test_nudge_minutes": ob.get("test_nudge_minutes", 3),
        "test_escalate_minutes": ob.get("test_escalate_minutes", 8),
    }
    if ob.get("welcome_message"):
        block["welcome_message"] = ob["welcome_message"]
    if ob.get("sheet_webhook"):
        block["sheet_webhook"] = ob["sheet_webhook"]     # Apps Script URL (see _lib/sheet.py)
    if ob.get("gate_role"):
        block["gate_role"] = ob["gate_role"]             # optional pre-onboarding holding role
    if ob.get("slack_channel"):
        block["slack_channel"] = ob["slack_channel"]     # else escalations use ace.slack_channel
    return block


def render_soul(spec: dict, template_path: Path | None = None) -> str:
    d = {**DEFAULTS, **spec}
    template_path = template_path or (Path(__file__).resolve().parents[1] / "templates" / "SOUL.md.tmpl")
    tmpl = template_path.read_text(encoding="utf-8")
    summary = "\n".join(
        f"- #{ch}: {behavior}" for ch, behavior in sorted(d["discord"]["channels"].items())
    )
    slack = spec.get("slack_channel") or _default_slack() or "#ace-escalations"
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
        # daily-digest posts to Slack itself (via _lib/slack_cli.py, brand-tagged) — no cron
        # delivery target; brand profiles have no Slack gateway, only the outbound bot token.
        {"name": "daily-digest", "schedule": "0 9 * * *", "skill": "daily-digest", "deliver": None,
         "prompt": "Run the daily digest exactly per the daily-digest skill: ONE command "
                   "(digest.py --post) — it posts to Slack itself. End with only [SILENT]."},
        {"name": "nudge-inactive", "schedule": "0 10 * * *", "skill": "nudge-inactive", "deliver": None},
        # Reply gating: zero-token pre-script; the agent runs ONLY when the script
        # surfaces unanswered creator messages ({"wakeAgent": false} otherwise).
        {"name": "sweep-unanswered", "schedule": "every 2m", "skill": "sweep-unanswered",
         "script": "ace-sweep.py", "deliver": "discord",
         "prompt": "Handle the unanswered creator messages surfaced above, following the "
                   "sweep-unanswered skill exactly. End with only [SILENT]."},
        # Onboarding (Vaulty replacement): zero-token pre-script handles joins/leavers/
        # engagement/escalations itself; the agent runs ONLY for 48h nudge composition.
        # Inert until ace.onboarding.enabled is flipped on.
        {"name": "onboarding-tick", "schedule": "every 2m", "skill": "run-onboarding",
         "script": "ace-onboarding-tick.py", "deliver": "discord",
         "prompt": "Send the onboarding nudges surfaced above, following the run-onboarding "
                   "skill (Nudge mode) exactly. End with only [SILENT]."},
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


# The complete creator-facing Discord toolset (allow-list — see _apply_security_defaults).
BRAND_DISCORD_TOOLSET = ["code_execution", "file", "skills", "vision"]

# Security hardening baseline applied to EVERY brand profile. These are forced
# (not setdefault) because they are the security posture, not a per-brand style
# choice — an operator who wants to loosen one after setup can hand-edit
# config.yaml; re-running setup-brand re-applies the baseline.
_SECURITY_COMMAND_ALLOWLIST_TEMPLATE = [
    "python3 {ace_root}/skills/*",
    "python3 {ace_root}/skills-admin/*",
    "python3 {profile_dir}/ace/*",
    "python3 {profile_dir}/skills/*",
    "hermes --profile {brand_id}",
    "hermes profile {brand_id}",
]


def _apply_security_defaults(existing: dict, spec: dict, profile_dir: "Path") -> None:
    """Force the validated security baseline onto a brand's config.yaml.

    Rationale (validated on test-brand, see SETUP_BRAND security incident notes):
      - approvals.mode=smart: brand agents get zero-friction approved-script
        execution but genuinely dangerous commands are still blocked/reviewed.
        NEVER 'off' — that disables all safety checks including for shell access.
      - code_execution.mode=strict: execute_code runs isolated, no project deps
        leak into the sandbox.
      - command_allowlist: scoped ONLY to this brand's own script paths + the
        shared Ace bundle — brand agents cannot run arbitrary shell commands.
      - terminal tool is REMOVED from discord/cli platform_toolsets: a brand
        support bot never needs a shell; it only needs its approved scripts,
        which run through execute_code / the allowlisted commands above.
      - session_reset=idle (60min): prevents a single long-running Discord
        session from accumulating poisoned context indefinitely. A stale
        session that once saw a leaked value or a bad instruction keeps
        repeating it turn after turn even after config/SOUL.md is fixed,
        because the fix only applies to NEW sessions. Idle reset guarantees
        every extended conversation eventually starts clean.
      - display.tool_progress=off / interim_assistant_messages=false: no
        tool-call/skill-loading chatter or command-approval prompts leak into
        the brand's Discord channel — the creator only sees the final answer.
    """
    ace_root = str(Path(__file__).resolve().parents[3])

    existing["approvals"] = {
        **(existing.get("approvals") or {}),
        "mode": "smart",
    }
    existing["code_execution"] = {
        **(existing.get("code_execution") or {}),
        "mode": "strict",
    }
    existing["command_allowlist"] = [
        p.format(ace_root=ace_root, profile_dir=str(profile_dir), brand_id=spec["brand_id"])
        for p in _SECURITY_COMMAND_ALLOWLIST_TEMPLATE
    ]
    existing["session_reset"] = {
        "mode": "idle",
        "idle_minutes": 60,
    }

    # The brand's creator-facing Discord toolset is an ALLOW-list, not a subtraction:
    # every extra tool is another LLM round trip the agent might spend, and each round
    # trip is 5–45s of creator-visible latency. These four cover every Ace flow —
    # scripts (code_execution), skill loading (skills), the odd file read (file), and
    # creator screenshots (vision). Everything else is removed on purpose:
    #   terminal/browser/web — shell + open internet: security and fabrication risk
    #   clarify              — emits "Hermes needs your input" and BLOCKS the turn
    #   cronjob              — a flailing agent self-scheduled jobs that spammed a thread
    #   delegation           — subagent spawning: the 6-minute replies
    #   memory/todo/session_search/tts — unused here; each is a wasted round trip
    platform_toolsets = existing.setdefault("platform_toolsets", {})
    platform_toolsets["discord"] = BRAND_DISCORD_TOOLSET
    cli = platform_toolsets.get("cli")
    if not isinstance(cli, list):
        cli = []
    platform_toolsets["cli"] = [t for t in cli if t not in {"terminal", "clarify"}]

    # Latency ceiling. Hermes defaults to 150 sequential tool round trips per reply;
    # a creator-facing support bot needs ~2. Measured in QA: one onboarding reply
    # burned 17 round trips over 6 minutes (mostly the agent retrying skill edits).
    # This caps the worst case at seconds, not minutes.
    agent_cfg = existing.setdefault("agent", {})
    agent_cfg["max_turns"] = int(agent_cfg.get("max_turns") or 0) or 8
    if agent_cfg["max_turns"] > 8:
        agent_cfg["max_turns"] = 8

    # The curator is a BACKGROUND agent that periodically reviews sessions and rewrites
    # skills/memory. On a brand profile it burns LLM calls and repeatedly tries to edit
    # the (root-owned, correctly read-only) shared bundle — 27 PermissionErrors in one
    # QA session. Brand skills are managed from git, never by the agent.
    existing.setdefault("curator", {})["enabled"] = False

    # Zero operational chatter in creator-facing chat: no tool progress, no mid-turn
    # notes, no file-verifier output, no turn explainers, no credits notices.
    display = existing.setdefault("display", {})
    display["tool_progress"] = "off"
    display["interim_assistant_messages"] = False
    display["file_mutation_verifier"] = False
    display["turn_completion_explainer"] = False
    display["credits_notices"] = False

    # Ascend operates on US Eastern: cron schedules ("0 9 * * *" = 9 AM), log timestamps,
    # and prompt time injection all follow this. IANA zone → DST handled by Hermes.
    # Hermes seeds `timezone: ""` (= server-local) on profile create, so treat empty as
    # unset; a deliberate per-brand IANA value survives re-runs.
    if not existing.get("timezone"):
        existing["timezone"] = "America/New_York"


def merge_config(config_path: str | Path, spec: dict) -> None:
    """Merge Ace's brand config into the profile config.yaml WITHOUT clobbering Hermes' own keys
    (model, skills.external_dirs, …). Ace metadata goes under `ace:`; the answer model is set at
    Hermes' top-level `model:` only when the spec specifies one (else the brand inherits the default).

    Also forces the security hardening baseline (see _apply_security_defaults) on every run —
    this is the one place brand security posture is enforced, so it must not be skippable by a
    stale or hand-edited config.yaml surviving a re-run.
    """
    import yaml  # PyYAML is a declared dep; needed to preserve existing Hermes config

    path = Path(config_path)
    existing = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    existing = existing or {}
    # The onboarding channel id is live Discord state written post-connect by
    # resolve_channels.py — keep it across spec-driven regeneration.
    prior_onboarding_channel = ((existing.get("ace") or {}).get("onboarding") or {}).get("channel_id")
    existing["ace"] = build_config(spec)
    if prior_onboarding_channel:
        existing["ace"]["onboarding"]["channel_id"] = prior_onboarding_channel
    if spec.get("model"):
        existing["model"] = spec["model"]  # Hermes reads top-level model; omit → inherit default
    _apply_security_defaults(existing, spec, path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")


def extract_channel_directory(soul_text: str) -> str | None:
    """Return the managed channel-directory block (markers included), or None."""
    start = soul_text.find(CHANNEL_DIR_START)
    end = soul_text.find(CHANNEL_DIR_END)
    if start == -1 or end == -1 or end < start:
        return None
    return soul_text[start : end + len(CHANNEL_DIR_END)]


def upsert_channel_directory(soul_text: str, block: str) -> str:
    """Insert or replace the managed channel-directory block in a SOUL.md text."""
    existing = extract_channel_directory(soul_text)
    if existing:
        return soul_text.replace(existing, block)
    return soul_text.rstrip("\n") + "\n\n" + block + "\n"


# Cron pre-scripts installed into <profile>/scripts/ — Hermes only runs cron scripts from
# there. Copied (not symlinked) so the profile is self-contained; a setup-brand re-run
# refreshes them, same as the rest of the baseline.
PROFILE_SCRIPTS = {
    "ace-sweep.py": "sweep-unanswered/scripts/sweep.py",
    "ace-onboarding-tick.py": "run-onboarding/scripts/onboarding_tick.py",
    "ace-join-listener.py": "run-onboarding/scripts/join_listener.py",
}


def install_sweep_script(profile: Path) -> None:
    skills_root = Path(__file__).resolve().parents[2]
    dest_dir = profile / "scripts"
    for dest_name, rel_src in PROFILE_SCRIPTS.items():
        src = skills_root / rel_src
        if not src.exists():
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / dest_name
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        dest.chmod(0o755)


def write_profile(spec: dict, profile_dir: str | Path) -> dict:
    validate_spec(spec)
    profile = Path(profile_dir)
    profile.mkdir(parents=True, exist_ok=True)
    config_path = profile / "config.yaml"
    soul_path = profile / "SOUL.md"
    cron_path = profile / "cronjobs.yaml"
    merge_config(config_path, spec)  # MERGE under `ace:` — preserves Hermes keys + external_dirs
    cron_path.write_text(json.dumps(build_cronjobs(spec), indent=2), encoding="utf-8")
    soul = render_soul(spec)
    if soul_path.exists():
        # Keep the post-connect channel directory (name → <#id> map) across re-runs:
        # it's derived from live Discord state resolve_channels.py owns, not from the spec.
        block = extract_channel_directory(soul_path.read_text(encoding="utf-8"))
        if block:
            soul = upsert_channel_directory(soul, block)
    soul_path.write_text(soul, encoding="utf-8")
    install_sweep_script(profile)
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
