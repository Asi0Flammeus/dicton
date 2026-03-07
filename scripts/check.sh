#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: ./scripts/check.sh [lint|test|build|all]

  lint   Run Ruff lint and formatting checks
  test   Run the pytest suite
  build  Build sdist and wheel via uv
  all    Run lint, test, and build (default)
EOF
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

run_lint() {
    require_cmd ruff
    echo "==> ruff check"
    ruff check .
    echo "==> ruff format --check"
    ruff format --check .
}

run_test() {
    require_cmd pytest
    echo "==> pytest"
    pytest "$@"
}

run_build() {
    require_cmd uv
    echo "==> uv build"
    uv build "$@"
}

main() {
    local target="${1:-all}"
    shift || true

    case "$target" in
        lint)
            run_lint
            ;;
        test)
            run_test "$@"
            ;;
        build)
            run_build "$@"
            ;;
        all)
            run_lint
            run_test "$@"
            run_build
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            usage >&2
            exit 1
            ;;
    esac
}

main "$@"
