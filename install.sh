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
# Builtin-only before any install command (no cat/dirname) so it runs on a bare
# host. External commands are only the orchestrator CLI + uv/pip, all guarded.
# ───────────────────────────────────────────────────────────────────────────────

SUPPORTED_ORCHESTRATORS=("hermes")
DEFAULT_ORCHESTRATOR="hermes"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  printf '%s\n' \
"Install the Ace skill bundle into an orchestrator." \
"" \
"Usage: ./install.sh [--orchestrator <name>] [--repo <path>] [--dry-run]" \
"" \
"Options:" \
"  --orchestrator <name>  Target orchestrator (default: ${DEFAULT_ORCHESTRATOR}). Supported: ${SUPPORTED_ORCHESTRATORS[*]}" \
"  --repo <path>          Bundle root to install (default: this repo)" \
"  --dry-run              Print the install commands without running them" \
"  -h, --help             Show this help" >&2
}

# this script lives at the repo root → repo root is its own dir (builtin-only)
REPO_ROOT="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
ORCHESTRATOR="${ACE_ORCHESTRATOR:-$DEFAULT_ORCHESTRATOR}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --orchestrator)   ORCHESTRATOR="${2:-}"; shift 2 ;;
    --orchestrator=*) ORCHESTRATOR="${1#*=}"; shift ;;
    --repo)           REPO_ROOT="${2:-}"; shift 2 ;;
    --repo=*)         REPO_ROOT="${1#*=}"; shift ;;
    --dry-run)        DRY_RUN=1; shift ;;
    -h|--help)        usage; exit 0 ;;
    *)                die "unknown argument: $1 (try --help)" ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }

# run a command, or just print it under --dry-run
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '  $ %s\n' "$*"
  else
    log "$*"
    "$@"
  fi
}

# install the script-only Python deps, if the orchestrator didn't already
install_script_deps() {
  local reqs="$REPO_ROOT/requirements-skills.txt"
  [[ -f "$reqs" ]] || return 0
  if have uv; then        run uv pip install -r "$reqs"
  elif have pip; then     run pip install -r "$reqs"
  elif have pip3; then    run pip3 install -r "$reqs"
  elif have python3; then run python3 -m pip install -r "$reqs"
  else warn "no uv/pip/python3 on PATH — install '$reqs' manually if the orchestrator didn't"; fi
}

# ── per-orchestrator adapters ──────────────────────────────────────────────────

install_hermes() {
  if ! have hermes; then
    [[ "$DRY_RUN" == "1" ]] \
      && warn "hermes CLI not on PATH (continuing because --dry-run)" \
      || die "hermes CLI not on PATH. Deploy/locate Hermes first, then re-run."
  fi
  log "Installing the Ace bundle into Hermes from: $REPO_ROOT"
  run hermes skills install "$REPO_ROOT"   # Hermes CLI — NOT npx, NOT pip
  install_script_deps
  printf '%s\n' \
"" \
"Bundle installed into Hermes. Next, per brand:" \
"  1. Create the brand's Hermes profile (attaches Discord/Slack tokens + OpenRouter key/model)." \
"  2. Run  /ace setup-brand  inside that profile, and drop in its knowledge.yaml." >&2
}

# ── main ───────────────────────────────────────────────────────────────────────

[[ -d "$REPO_ROOT/skills" ]] || die "no skills/ under repo root: '$REPO_ROOT' (pass --repo)"

case "$ORCHESTRATOR" in
  hermes) install_hermes ;;
  *)      die "unsupported orchestrator: '$ORCHESTRATOR' (supported: ${SUPPORTED_ORCHESTRATORS[*]})." ;;
esac
