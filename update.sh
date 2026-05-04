#!/usr/bin/env bash
# Build, install, and restart Dicton in one step.
#
# Pipeline:
#   1. Build the Debian package via scripts/prepare_local_release.sh
#      (handles isolated venv + PyInstaller). Lint and tests are skipped
#      by default for fast iteration; pass --full to run them.
#   2. Install (or upgrade) the resulting .deb via sudo apt install (resolves
#      runtime deps automatically). The packaged postinst takes care of
#      stopping the running daemon and restarting it; if for some reason it
#      didn't, this script also respawns as a fallback.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${PROJECT_DIR}/dist"
DAEMON_BIN="/opt/dicton/dicton"
LOG_FILE="/tmp/dicton-deb.log"

run_full=false
for arg in "$@"; do
    case "$arg" in
        --full) run_full=true ;;
        -h|--help)
            echo "Usage: $(basename "$0") [--full]"
            echo "  --full   Run lint and tests as well (default skips both)."
            exit 0
            ;;
        *)
            echo "Unknown flag: $arg" >&2
            exit 2
            ;;
    esac
done

cd "${PROJECT_DIR}"

# 1. Build (delegates to prepare_local_release.sh which sets up the venv)
echo "==> Building .deb"
release_args=()
if [[ "$run_full" == false ]]; then
    release_args+=(--skip-lint --skip-tests)
fi
"${PROJECT_DIR}/scripts/prepare_local_release.sh" "${release_args[@]}"

# 2. Install — pick the freshest .deb in dist/
deb_path="$(ls -1t "${DIST_DIR}"/dicton_*_amd64.deb 2>/dev/null | head -n1)"
if [[ -z "${deb_path}" ]]; then
    echo "ERROR: no .deb found in ${DIST_DIR}" >&2
    exit 1
fi

echo "==> Installing $(basename "${deb_path}")"
sudo apt install -y "${deb_path}"

# 3. Verify daemon is up (postinst should have respawned it)
sleep 2
new_pid="$(pgrep -u "${USER}" -f "${DAEMON_BIN}" | head -n1 || true)"

if [[ -z "${new_pid}" ]]; then
    # Fallback: respawn manually if postinst didn't restart for some reason
    echo "==> postinst didn't restart daemon — spawning fallback"
    setsid "${DAEMON_BIN}" </dev/null >"${LOG_FILE}" 2>&1 &
    disown
    sleep 2
    new_pid="$(pgrep -u "${USER}" -f "${DAEMON_BIN}" | head -n1 || true)"
fi

if [[ -n "${new_pid}" ]]; then
    echo "==> Daemon up: PID ${new_pid}"
    echo "    Version: $(dpkg-query -W -f='${Version}' dicton 2>/dev/null || echo '?')"
else
    echo "ERROR: daemon failed to start — check ${LOG_FILE}" >&2
    exit 1
fi
