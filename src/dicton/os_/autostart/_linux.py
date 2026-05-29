"""Linux backend: systemd --user unit."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SYSTEMD_UNIT = """[Unit]
Description=dicton voice dictation

[Service]
Type=simple
ExecStart={exec_path} --foreground
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
"""


def _exec_path() -> str:
    found = shutil.which("dicton")
    return found or "dicton"


def enable() -> bool:
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / "dicton.service"
    unit_path.write_text(SYSTEMD_UNIT.format(exec_path=_exec_path()), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", "dicton.service"], check=False)
    return True


def disable() -> bool:
    subprocess.run(["systemctl", "--user", "disable", "--now", "dicton.service"], check=False)
    unit_path = Path.home() / ".config" / "systemd" / "user" / "dicton.service"
    unit_path.unlink(missing_ok=True)
    return True
