#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PROJECT_DIR}/dist"
STAGE_DIR="${PROJECT_DIR}/build/linux-deb"
BUNDLE_DIR="${DIST_DIR}/dicton"

cd "${PROJECT_DIR}"

version="$(python3 - <<'PY'
import re
from pathlib import Path

content = Path("src/dicton/__init__.py").read_text(encoding="utf-8")
match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
if not match:
    raise SystemExit("Unable to determine Dicton version")
print(match.group(1))
PY
)"

echo "==> Building Dicton Linux bundle"
python3 -m PyInstaller --noconfirm --clean packaging/linux/dicton.spec

if [[ ! -d "${BUNDLE_DIR}" ]]; then
    echo "Expected bundle directory not found: ${BUNDLE_DIR}" >&2
    exit 1
fi

tarball_path="${DIST_DIR}/dicton-linux-x64.tar.gz"
echo "==> Creating Linux tarball: ${tarball_path}"
tar -C "${DIST_DIR}" -czf "${tarball_path}" dicton

echo "==> Creating Debian package staging area"
rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}/DEBIAN" "${STAGE_DIR}/opt/dicton" "${STAGE_DIR}/usr/bin"

cp -a "${BUNDLE_DIR}/." "${STAGE_DIR}/opt/dicton/"

cat > "${STAGE_DIR}/usr/bin/dicton" <<'EOF'
#!/bin/sh
exec /opt/dicton/dicton "$@"
EOF
chmod 0755 "${STAGE_DIR}/usr/bin/dicton"

cat > "${STAGE_DIR}/DEBIAN/control" <<EOF
Package: dicton
Version: ${version}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: asi0 flammeus <asi0@crqpt.com>
Depends: libportaudio2, xdotool, libnotify-bin
Recommends: xclip | wl-clipboard
Description: Voice-to-text dictation with direct transcription and translation
 Dicton is a desktop dictation tool focused on direct transcription and
 translation to English, packaged here as a Linux one-folder bundle.
EOF

deb_path="${DIST_DIR}/dicton_${version}_amd64.deb"
echo "==> Building Debian package: ${deb_path}"
dpkg-deb --build --root-owner-group "${STAGE_DIR}" "${deb_path}"

echo "==> Linux release assets ready:"
echo "    ${tarball_path}"
echo "    ${deb_path}"
