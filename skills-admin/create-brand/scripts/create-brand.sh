#!/usr/bin/env bash
set -euo pipefail

# Create + register a new brand profile, and (optionally) write its Ace config from a spec.
# Thin wrapper so the create/config logic lives in one place:
#   - install.sh --profile <name> --create     (profile + register brand skills)
#   - setup-brand/scripts/setup.py --spec ...  (channel scoping + model + SOUL + cron + ACE_DATA_DIR)
#
# Usage: create-brand.sh <name> [--spec <brand.json>] [--dry-run]

# this script: <repo>/skills-admin/create-brand/scripts/create-brand.sh → repo root is 3 up
SELF="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
REPO="$(cd "$SELF/../../.." && pwd)"
HERMES_HOME="${HERMES_HOME:-${HOME:-/root}/.hermes}"

name=""; spec=""; dry=0; passthru=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --spec)    spec="${2:-}"; shift 2 ;;
    --spec=*)  spec="${1#*=}"; shift ;;
    --dry-run) dry=1; passthru+=("--dry-run"); shift ;;
    -*)        passthru+=("$1"); shift ;;
    *)         if [[ -z "$name" ]]; then name="$1"; else passthru+=("$1"); fi; shift ;;
  esac
done
[[ -n "$name" ]] || { printf 'usage: create-brand.sh <name> [--spec <brand.json>] [--dry-run]\n' >&2; exit 2; }

# 1. create the profile + register the per-brand skills
"$REPO/install.sh" --profile "$name" --create ${passthru[@]+"${passthru[@]}"}

# 2. if a config spec was provided, write the brand's Ace config into the profile
if [[ -n "$spec" ]]; then
  profile_dir="$HERMES_HOME/profiles/$name"
  setup="$REPO/skills/setup-brand/scripts/setup.py"
  if [[ "$dry" == "1" ]]; then
    printf '  $ python3 %s --spec %s --profile-dir %s\n' "$setup" "$spec" "$profile_dir"
  else
    python3 "$setup" --spec "$spec" --profile-dir "$profile_dir"
  fi
fi
