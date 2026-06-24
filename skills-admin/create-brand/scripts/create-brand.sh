#!/usr/bin/env bash
set -euo pipefail

# Create + register a new brand profile. Thin wrapper over the bundle installer so the
# create logic lives in one place (install.sh --profile <name> --create).
#
# Usage: create-brand.sh <name> [extra install.sh args]

# this script: <repo>/skills-admin/create-brand/scripts/create-brand.sh → repo root is 3 up
SELF="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
REPO="$(cd "$SELF/../../.." && pwd)"

[[ -n "${1:-}" ]] || { printf 'usage: create-brand.sh <name>\n' >&2; exit 2; }
name="$1"; shift

exec "$REPO/install.sh" --profile "$name" --create "$@"
