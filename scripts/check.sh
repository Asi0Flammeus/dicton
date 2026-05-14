#!/usr/bin/env bash
# Repository validation entrypoint.
# Usage: ./scripts/check.sh [lint|test|all]
set -euo pipefail

cmd="${1:-all}"

run_lint() {
    echo "» ruff check"
    uv run ruff check src tests
    echo "» ruff format --check"
    uv run ruff format --check src tests
    echo "» pipeline.py LOC cap (≤300)"
    loc=$(wc -l < src/dicton/pipeline.py)
    if [ "$loc" -gt 300 ]; then
        echo "FAIL: pipeline.py is $loc lines (cap 300)"
        exit 1
    fi
    echo "  pipeline.py: $loc lines — OK"
}

run_test() {
    echo "» pytest"
    uv run pytest
}

case "$cmd" in
    lint) run_lint ;;
    test) run_test ;;
    all)  run_lint && run_test ;;
    *) echo "unknown: $cmd"; exit 2 ;;
esac
