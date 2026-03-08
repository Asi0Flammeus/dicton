#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# prepare_local_release.sh — reproduce the CI release pipeline locally
#
# Mirrors the GitHub Actions release.yml linux-package job so you can
# validate the .deb before pushing a PR.
#
# Usage:
#   ./scripts/prepare_local_release.sh              # full pipeline
#   ./scripts/prepare_local_release.sh --skip-lint   # skip lint step
#   ./scripts/prepare_local_release.sh --skip-tests  # skip test step
#   ./scripts/prepare_local_release.sh --install      # install .deb after build
# ──────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Flags ─────────────────────────────────────────────────
skip_lint=false
skip_tests=false
do_install=false

for arg in "$@"; do
    case "$arg" in
        --skip-lint)  skip_lint=true ;;
        --skip-tests) skip_tests=true ;;
        --install)    do_install=true ;;
        -h|--help)
            cat <<'EOF'
Usage: ./scripts/prepare_local_release.sh [OPTIONS]

Reproduce the CI release pipeline locally to validate the .deb package.

Options:
  --skip-lint    Skip ruff lint/format checks
  --skip-tests   Skip pytest suite
  --install      Install the .deb after a successful build
  -h, --help     Show this help
EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 1
            ;;
    esac
done

cd "${PROJECT_DIR}"

# ── Helpers ───────────────────────────────────────────────
step() { echo -e "\n\033[1;34m==> $1\033[0m"; }
ok()   { echo -e "\033[1;32m    ✔ $1\033[0m"; }
fail() { echo -e "\033[1;31m    ✘ $1\033[0m" >&2; exit 1; }

# ── 1. Check system dependencies ─────────────────────────
step "Checking system dependencies"

missing=()
for pkg in libportaudio2 xdotool libnotify-bin dpkg-deb; do
    if [[ "$pkg" == "dpkg-deb" ]]; then
        command -v dpkg-deb >/dev/null 2>&1 || missing+=("dpkg")
    else
        dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    fi
done

# Build-time dep (header files for PyAudio compilation)
dpkg -s portaudio19-dev >/dev/null 2>&1 || missing+=("portaudio19-dev")

if [[ ${#missing[@]} -gt 0 ]]; then
    fail "Missing system packages: ${missing[*]}
    Install with:  sudo apt-get install -y ${missing[*]}"
fi
ok "All system dependencies present"

# ── 2. Check Python ──────────────────────────────────────
step "Checking Python"

python_bin=""
for candidate in python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        python_bin="$candidate"
        break
    fi
done

if [[ -z "$python_bin" ]]; then
    fail "python3 not found"
fi

py_version="$("$python_bin" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
ok "Using $python_bin ($py_version)"

# ── 3. Set up a clean venv ───────────────────────────────
step "Setting up build venv"

BUILD_VENV="${PROJECT_DIR}/build/release-venv"
if [[ -d "$BUILD_VENV" ]]; then
    rm -rf "$BUILD_VENV"
fi

"$python_bin" -m venv "$BUILD_VENV"
# shellcheck disable=SC1091
source "${BUILD_VENV}/bin/activate"
pip install --upgrade pip >/dev/null
ok "Clean venv at ${BUILD_VENV}"

# ── 4. Install project with linux + packaging extras ─────
step "Installing dicton[linux,packaging]"
pip install -e ".[linux,packaging]" 2>&1 | tail -1
ok "Dependencies installed"

# ── 5. Lint ──────────────────────────────────────────────
if [[ "$skip_lint" == false ]]; then
    step "Running lint checks"
    ./scripts/check.sh lint
    ok "Lint passed"
else
    step "Skipping lint (--skip-lint)"
fi

# ── 6. Tests ─────────────────────────────────────────────
if [[ "$skip_tests" == false ]]; then
    step "Running tests"
    ./scripts/check.sh test
    ok "Tests passed"
else
    step "Skipping tests (--skip-tests)"
fi

# ── 7. Build Python dist (sdist + wheel) ─────────────────
step "Building Python dist"
pip install uv >/dev/null 2>&1 || true
./scripts/check.sh build
ok "sdist + wheel built"

# ── 8. Build Linux package (.tar.gz + .deb) ──────────────
step "Building Linux package"
./scripts/build-linux-package.sh

tar_path="${PROJECT_DIR}/dist/dicton-linux-x64.tar.gz"
deb_path="$(ls "${PROJECT_DIR}"/dist/dicton_*_amd64.deb 2>/dev/null | head -1)"

[[ -f "$tar_path" ]] || fail "tarball not found"
[[ -n "$deb_path" && -f "$deb_path" ]] || fail ".deb not found in dist/"
version="$(dpkg-deb --field "$deb_path" Version)"
ok ".deb and tarball created (v${version})"

# ── 9. Smoke test the PyInstaller bundle ─────────────────
step "Smoke testing packaged binary"
bundle_version="$(./dist/dicton/dicton --version 2>&1)"
ok "Binary runs: ${bundle_version}"

# ── 10. Validate .deb metadata ──────────────────────────
step "Validating .deb package"
dpkg-deb --info "$deb_path" >/dev/null
deb_contents="$(dpkg-deb --contents "$deb_path")"
echo "$deb_contents" | grep -q "opt/dicton/dicton" \
    || fail ".deb missing /opt/dicton/dicton binary"
echo "$deb_contents" | grep -q "usr/bin/dicton" \
    || fail ".deb missing /usr/bin/dicton wrapper"
ok ".deb structure valid"

# ── 11. Optional install ────────────────────────────────
if [[ "$do_install" == true ]]; then
    step "Installing .deb"
    sudo dpkg -i "$deb_path" || sudo apt-get install -f -y
    installed_version="$(dicton --version 2>&1)"
    ok "Installed: ${installed_version}"
fi

# ── Summary ──────────────────────────────────────────────
deactivate 2>/dev/null || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Release artifacts ready (v${version})"
echo ""
echo "  .deb:     ${deb_path}"
echo "  tarball:  ${tar_path}"
echo "  wheel:    dist/dicton-${version}-py3-none-any.whl"
echo ""
echo "  Install:  sudo dpkg -i ${deb_path}"
echo "  Test:     dicton --version"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
