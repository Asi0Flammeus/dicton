#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# dev.sh — run dicton from source (editable install)
#
# Usage:
#   ./scripts/dev.sh              # install editable + launch
#   ./scripts/dev.sh --skip-install  # just launch (already installed)
#   ./scripts/dev.sh --debug      # launch with DEBUG=true
# ──────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

skip_install=false
extra_args=()

for arg in "$@"; do
    case "$arg" in
        --skip-install) skip_install=true ;;
        --debug)        export DEBUG=true ;;
        -h|--help)
            cat <<'EOF'
Usage: ./scripts/dev.sh [OPTIONS] [-- DICTON_ARGS...]

Run dicton from source with an editable install.

Options:
  --skip-install   Skip pip install -e (use if already installed)
  --debug          Set DEBUG=true for verbose output
  -h, --help       Show this help

Examples:
  ./scripts/dev.sh                    # full editable install + run
  ./scripts/dev.sh --skip-install     # just run (faster iteration)
  ./scripts/dev.sh --debug            # run with debug logging
  ./scripts/dev.sh -- --version       # pass args to dicton
EOF
            exit 0
            ;;
        --)  shift; extra_args=("$@"); break ;;
        *)   extra_args+=("$arg") ;;
    esac
done

cd "${PROJECT_DIR}"

# Activate project venv if not already in one
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    for candidate in .venv venv env; do
        if [[ -f "${PROJECT_DIR}/${candidate}/bin/activate" ]]; then
            echo "==> Activating ${candidate}"
            # shellcheck disable=SC1091
            source "${PROJECT_DIR}/${candidate}/bin/activate"
            break
        fi
    done
fi

if [[ "$skip_install" == false ]]; then
    echo "==> Installing dicton (editable)..."
    pip install -e ".[linux,dev]" --quiet 2>&1 | tail -1
    echo "    done."
fi

echo "==> Launching dicton from source"
exec python -m dicton "${extra_args[@]}"
