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
#   ./scripts/prepare_local_release.sh --verbose      # show subprocess output
# ──────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${PROJECT_DIR}/build/release.log"

# ── Flags ─────────────────────────────────────────────────
skip_lint=false
skip_tests=false
do_install=false
verbose=false

for arg in "$@"; do
    case "$arg" in
        --skip-lint)  skip_lint=true ;;
        --skip-tests) skip_tests=true ;;
        --install)    do_install=true ;;
        --verbose)    verbose=true ;;
        -h|--help)
            cat <<'EOF'
Usage: ./scripts/prepare_local_release.sh [OPTIONS]

Reproduce the CI release pipeline locally to validate the .deb package.

Options:
  --skip-lint    Skip ruff lint/format checks
  --skip-tests   Skip pytest suite
  --install      Install the .deb after a successful build
  --verbose      Show full subprocess output
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
mkdir -p build

# ── Terminal setup ────────────────────────────────────────
BOLD="\033[1m"
DIM="\033[2m"
RST="\033[0m"
RED="\033[1;31m"
GRN="\033[1;32m"
YLW="\033[1;33m"
BLU="\033[1;34m"
CYN="\033[0;36m"
CLEAR_LINE="\033[2K\r"

ROWS="$(tput lines 2>/dev/null || echo 24)"
HEADER_ROWS=3  # banner + progress bar + separator

# ── Step tracking ─────────────────────────────────────────
TOTAL_STEPS=8
[[ "$skip_lint"  == true ]] && TOTAL_STEPS=$((TOTAL_STEPS - 1))
[[ "$skip_tests" == true ]] && TOTAL_STEPS=$((TOTAL_STEPS - 1))
[[ "$do_install" == true ]] && TOTAL_STEPS=$((TOTAL_STEPS + 1))
CURRENT_STEP=0
CURRENT_PHASE=""
PIPELINE_START="$(date +%s)"

# ── UI core ───────────────────────────────────────────────
_elapsed() {
    local start=$1
    local now; now="$(date +%s)"
    local secs=$((now - start))
    if (( secs < 60 )); then
        printf "%ds" "$secs"
    else
        printf "%dm%02ds" $((secs / 60)) $((secs % 60))
    fi
}

_render_header() {
    local pct=$(( TOTAL_STEPS > 0 ? (CURRENT_STEP * 100) / TOTAL_STEPS : 0 ))
    local filled=$(( (pct * 30) / 100 ))
    local empty=$(( 30 - filled ))
    local total_el; total_el="$(_elapsed "$PIPELINE_START")"

    local bar="${GRN}"
    for ((i = 0; i < filled; i++)); do bar+="━"; done
    bar+="${DIM}"
    for ((i = 0; i < empty;  i++)); do bar+="━"; done
    bar+="${RST}"

    # save cursor, jump to top, draw header, restore cursor
    printf "\033[s"
    printf "\033[1;1H\033[2K"
    printf "  ${BLU}${BOLD}Dicton${RST} — Local Release Builder          ${DIM}%s${RST}" "$total_el"
    printf "\033[2;1H\033[2K"
    printf "  %b %3d%%  ${DIM}[%d/%d]${RST}  ${CYN}%s${RST}" "$bar" "$pct" "$CURRENT_STEP" "$TOTAL_STEPS" "$CURRENT_PHASE"
    printf "\033[3;1H\033[2K"
    printf "  ${DIM}%0.s─${RST}" {1..45}
    printf "\033[u"
}

_setup_layout() {
    # print 3 blank lines for the header area
    printf "\n\n\n"
    # set scroll region: lines below header to bottom
    printf "\033[%d;%dr" $((HEADER_ROWS + 1)) "$ROWS"
    # move cursor into the scroll region
    printf "\033[%d;1H" $((HEADER_ROWS + 1))
    _render_header
}

_teardown_layout() {
    # reset scroll region to full terminal
    printf "\033[;r"
    # move cursor below content
    printf "\033[%d;1H" "$ROWS"
}

_header() {
    CURRENT_PHASE="$1"
    _render_header
    echo -e "  ${BLU}${BOLD}$1${RST}"
}

_spinner() {
    local pid=$1
    local label=$2
    local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
    local i=0
    local start; start="$(date +%s)"
    while kill -0 "$pid" 2>/dev/null; do
        local elapsed; elapsed="$(_elapsed "$start")"
        printf "${CLEAR_LINE}  ${CYN}${frames[$i]}${RST} ${DIM}%-40s %s${RST}" "$label" "$elapsed" >&2
        _render_header
        i=$(( (i + 1) % ${#frames[@]} ))
        sleep 0.1
    done
    printf "${CLEAR_LINE}" >&2
}

_run() {
    local label="$1"
    shift
    local start; start="$(date +%s)"

    if [[ "$verbose" == true ]]; then
        echo -e "  ${DIM}$ $*${RST}"
        "$@" 2>&1 | tee -a "$LOG_FILE"
        local rc=${PIPESTATUS[0]}
    else
        "$@" >> "$LOG_FILE" 2>&1 &
        local pid=$!
        _spinner "$pid" "$label"
        wait "$pid"
        local rc=$?
    fi

    local elapsed; elapsed="$(_elapsed "$start")"
    if [[ $rc -eq 0 ]]; then
        echo -e "  ${GRN}✔${RST} ${label}  ${DIM}${elapsed}${RST}"
    else
        echo -e "  ${RED}✘${RST} ${label}  ${DIM}${elapsed}${RST}"
        echo ""
        echo -e "  ${RED}${BOLD}Failed.${RST} ${DIM}Full log: ${LOG_FILE}${RST}"
        if [[ "$verbose" == false ]]; then
            echo -e "  ${DIM}Last 15 lines:${RST}"
            tail -15 "$LOG_FILE" | sed 's/^/    /'
        fi
        _teardown_layout
        exit 1
    fi
}

_skip() {
    echo -e "  ${YLW}⊘${RST} ${DIM}$1  skipped${RST}"
}

# ── Start ─────────────────────────────────────────────────
: > "$LOG_FILE"
_setup_layout

# ── 1. System dependencies ───────────────────────────────
CURRENT_STEP=$((CURRENT_STEP + 1))
_header "Preflight checks"

missing=()
for pkg in libportaudio2 xdotool libnotify-bin; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
command -v dpkg-deb >/dev/null 2>&1 || missing+=("dpkg")
dpkg -s portaudio19-dev >/dev/null 2>&1 || missing+=("portaudio19-dev")

if [[ ${#missing[@]} -gt 0 ]]; then
    echo -e "  ${RED}✘${RST} Missing system packages: ${BOLD}${missing[*]}${RST}"
    echo -e "  ${DIM}  sudo apt-get install -y ${missing[*]}${RST}"
    _teardown_layout
    exit 1
fi
echo -e "  ${GRN}✔${RST} System dependencies"

python_bin=""
for candidate in python3.11 python3; do
    command -v "$candidate" >/dev/null 2>&1 && { python_bin="$candidate"; break; }
done
if [[ -z "$python_bin" ]]; then
    echo -e "  ${RED}✘${RST} python3 not found"
    _teardown_layout
    exit 1
fi

py_version="$("$python_bin" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo -e "  ${GRN}✔${RST} Python ${py_version}  ${DIM}($python_bin)${RST}"

# ── 2. Clean venv ────────────────────────────────────────
CURRENT_STEP=$((CURRENT_STEP + 1))
_header "Environment setup"

BUILD_VENV="${PROJECT_DIR}/build/release-venv"
[[ -d "$BUILD_VENV" ]] && rm -rf "$BUILD_VENV"
_run "Creating isolated venv" "$python_bin" -m venv "$BUILD_VENV"

# shellcheck disable=SC1091
source "${BUILD_VENV}/bin/activate"
_run "Upgrading pip" pip install --upgrade pip

# ── 3. Install dependencies ─────────────────────────────
CURRENT_STEP=$((CURRENT_STEP + 1))
_header "Installing dependencies"
_run "dicton[linux,packaging]" pip install -e ".[linux,packaging]"
_run "uv (build backend)" pip install uv

# ── 4. Lint ──────────────────────────────────────────────
CURRENT_STEP=$((CURRENT_STEP + 1))
if [[ "$skip_lint" == false ]]; then
    _header "Code quality"
    _run "ruff check" ruff check .
    _run "ruff format --check" ruff format --check .
else
    _header "Code quality"
    _skip "Lint"
fi

# ── 5. Tests ─────────────────────────────────────────────
if [[ "$skip_tests" == false ]]; then
    CURRENT_STEP=$((CURRENT_STEP + 1))
    _header "Test suite"
    _run "pytest" pytest
fi

# ── 6. Python dist ──────────────────────────────────────
CURRENT_STEP=$((CURRENT_STEP + 1))
_header "Python distribution"
_run "sdist + wheel" uv build

# ── 7. Linux package ────────────────────────────────────
CURRENT_STEP=$((CURRENT_STEP + 1))
_header "Linux packaging"
_run "PyInstaller bundle + .deb" ./scripts/build-linux-package.sh

tar_path="${PROJECT_DIR}/dist/dicton-linux-x64.tar.gz"
deb_path="$(ls "${PROJECT_DIR}"/dist/dicton_*_amd64.deb 2>/dev/null | head -1)"

[[ -f "$tar_path" ]] || { echo -e "  ${RED}✘${RST} Tarball not found"; _teardown_layout; exit 1; }
[[ -n "$deb_path" && -f "$deb_path" ]] || { echo -e "  ${RED}✘${RST} .deb not found in dist/"; _teardown_layout; exit 1; }

version="$(dpkg-deb --field "$deb_path" Version)"

# ── 8. Validation ───────────────────────────────────────
CURRENT_STEP=$((CURRENT_STEP + 1))
_header "Smoke tests & validation"

bundle_version="$(./dist/dicton/dicton --version 2>&1)"
echo -e "  ${GRN}✔${RST} Binary runs  ${DIM}(${bundle_version})${RST}"

dpkg-deb --info "$deb_path" >/dev/null
deb_contents="$(dpkg-deb --contents "$deb_path")"
echo "$deb_contents" | grep -q "opt/dicton/dicton" \
    || { echo -e "  ${RED}✘${RST} .deb missing /opt/dicton/dicton"; _teardown_layout; exit 1; }
echo "$deb_contents" | grep -q "usr/bin/dicton" \
    || { echo -e "  ${RED}✘${RST} .deb missing /usr/bin/dicton"; _teardown_layout; exit 1; }
echo -e "  ${GRN}✔${RST} .deb structure valid"

deb_size="$(du -h "$deb_path" | cut -f1)"
tar_size="$(du -h "$tar_path" | cut -f1)"

# ── 9. Optional install ────────────────────────────────
if [[ "$do_install" == true ]]; then
    CURRENT_STEP=$((CURRENT_STEP + 1))
    _header "Installing package"
    sudo dpkg -i "$deb_path" || sudo apt-get install -f -y
    installed_version="$(dicton --version 2>&1)"
    echo -e "  ${GRN}✔${RST} Installed  ${DIM}(${installed_version})${RST}"
fi

# ── Summary ──────────────────────────────────────────────
deactivate 2>/dev/null || true

CURRENT_PHASE="Done"
_render_header

deb_name="${deb_path##*/}"
total_elapsed="$(_elapsed "$PIPELINE_START")"

echo ""
echo -e "  ${GRN}${BOLD}Build complete${RST}  v${version}  ${DIM}${total_elapsed}${RST}"
echo ""
echo -e "  ${DIM}Artifacts:${RST}"
echo -e "    .deb      ${deb_name}  ${DIM}(${deb_size})${RST}"
echo -e "    tarball   dicton-linux-x64.tar.gz  ${DIM}(${tar_size})${RST}"
echo ""
echo -e "  ${DIM}Install:${RST}  ${CYN}sudo dpkg -i ${deb_name}${RST}"
echo -e "  ${DIM}Log:${RST}      build/release.log"

_teardown_layout
echo ""
