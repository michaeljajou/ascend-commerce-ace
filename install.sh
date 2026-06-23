#!/usr/bin/env bash
set -euo pipefail

# ── Ace skill-bundle installer ─────────────────────────────────────────────────
# One command to install this bundle into an orchestrator. Installs differ per
# orchestrator, so you tell it which one (default: hermes). Only Hermes is
# supported today — add another by listing it in SUPPORTED_ORCHESTRATORS and
# writing an `install_<name>` adapter below.
#
#   git clone <repo> ace && cd ace && ./install.sh
#
# Hermes has no whole-repo / local-path skill install, and no shared-library
# convention — so we register this repo's skills/ dir as an `external_dirs`
# source in Hermes' config. Hermes then discovers all skills in place (and
# ignores skills/_lib, since it starts with "_"), our scripts import _lib as a
# sibling, and updates are just `git pull`. The clone IS the install — keep it.
# ───────────────────────────────────────────────────────────────────────────────

SUPPORTED_ORCHESTRATORS=("hermes")
DEFAULT_ORCHESTRATOR="hermes"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# this script lives at the repo root → repo root is its own dir (builtin-only)
REPO_ROOT="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
ORCHESTRATOR="${ACE_ORCHESTRATOR:-$DEFAULT_ORCHESTRATOR}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_CONFIG="${HERMES_CONFIG:-$HERMES_HOME/config.yaml}"
DRY_RUN=0
NO_DEPS=0

usage() {
  printf '%s\n' \
"Install the Ace skill bundle into an orchestrator." \
"" \
"Usage: ./install.sh [--orchestrator <name>] [--repo <path>] [--dry-run] [--no-deps]" \
"" \
"Options:" \
"  --orchestrator <name>  Target orchestrator (default: ${DEFAULT_ORCHESTRATOR}). Supported: ${SUPPORTED_ORCHESTRATORS[*]}" \
"  --repo <path>          Bundle root to install (default: this repo)" \
"  --hermes-config <path> Hermes config.yaml to update (default: \$HERMES_HOME/config.yaml)" \
"  --no-deps              Skip installing the script-only Python deps" \
"  --dry-run              Print what it would do without changing anything" \
"  -h, --help             Show this help" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --orchestrator)    ORCHESTRATOR="${2:-}"; shift 2 ;;
    --orchestrator=*)  ORCHESTRATOR="${1#*=}"; shift ;;
    --repo)            REPO_ROOT="${2:-}"; shift 2 ;;
    --repo=*)          REPO_ROOT="${1#*=}"; shift ;;
    --hermes-config)   HERMES_CONFIG="${2:-}"; shift 2 ;;
    --hermes-config=*) HERMES_CONFIG="${1#*=}"; shift ;;
    --no-deps)         NO_DEPS=1; shift ;;
    --dry-run)         DRY_RUN=1; shift ;;
    -h|--help)         usage; exit 0 ;;
    *)                 die "unknown argument: $1 (try --help)" ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }

run() {  # run a command, or just print it under --dry-run
  if [[ "$DRY_RUN" == "1" ]]; then printf '  $ %s\n' "$*"; else log "$*"; "$@"; fi
}

# install the script-only Python deps, if the orchestrator didn't already
install_script_deps() {
  [[ "$NO_DEPS" == "1" ]] && { log "skipping deps (--no-deps)"; return 0; }
  local reqs="$REPO_ROOT/requirements-skills.txt"
  [[ -f "$reqs" ]] || return 0
  if have uv; then        run uv pip install -r "$reqs"
  elif have pip; then     run pip install -r "$reqs"
  elif have pip3; then    run pip3 install -r "$reqs"
  elif have python3; then run python3 -m pip install -r "$reqs"
  else warn "no uv/pip/python3 on PATH — install '$reqs' manually if the orchestrator didn't"; fi
}

# ── per-orchestrator adapters ──────────────────────────────────────────────────

# Idempotently add "$1" to skills.external_dirs in the Hermes config (YAML).
register_external_dir() {
  local skills_dir="$1"
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '  + register external skills dir in %s\n' "$HERMES_CONFIG"
    printf '      skills.external_dirs += %s\n' "$skills_dir"
    return 0
  fi
  log "Registering external skills dir in $HERMES_CONFIG"
  ACE_CFG="$HERMES_CONFIG" ACE_SKILLS_DIR="$skills_dir" "${ACE_PYTHON:-python3}" - <<'PY'
import os, sys, pathlib
cfg = pathlib.Path(os.environ["ACE_CFG"])
skills_dir = os.environ["ACE_SKILLS_DIR"]
try:
    import yaml
except ImportError:
    sys.stderr.write("error: PyYAML not available — run without --no-deps, or "
                     "`pip install pyyaml`, then re-run.\n")
    sys.exit(3)
data = yaml.safe_load(cfg.read_text()) if cfg.exists() else None
data = data or {}
skills = data.setdefault("skills", {})
dirs = skills.setdefault("external_dirs", [])
if skills_dir in dirs:
    print(f"already registered: {skills_dir}")
else:
    dirs.append(skills_dir)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(yaml.safe_dump(data, sort_keys=False))
    print(f"registered: {skills_dir}")
PY
}

install_hermes() {
  install_script_deps
  register_external_dir "$REPO_ROOT/skills"
  printf '%s\n' \
"" \
"Ace skills registered with Hermes (external_dirs → $REPO_ROOT/skills)." \
"Keep this clone in place — Hermes loads the skills from here; update with: git pull" \
"" \
"Next, per brand:" \
"  1. Create the brand's Hermes profile (attaches Discord/Slack tokens + OpenRouter key/model)." \
"  2. Run  /ace setup-brand  inside that profile, and drop in its knowledge.yaml." >&2
}

# ── main ───────────────────────────────────────────────────────────────────────

[[ -d "$REPO_ROOT/skills" ]] || die "no skills/ under repo root: '$REPO_ROOT' (pass --repo)"

case "$ORCHESTRATOR" in
  hermes) install_hermes ;;
  *)      die "unsupported orchestrator: '$ORCHESTRATOR' (supported: ${SUPPORTED_ORCHESTRATORS[*]})." ;;
esac
