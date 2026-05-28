"""macOS backend: ~/Library/LaunchAgents plist."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

LAUNCHD_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>cat.dicton</string>
  <key>ProgramArguments</key>
  <array><string>{exec_path}</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
"""


def _exec_path() -> str:
    found = shutil.which("dicton")
    return found or "dicton"


def enable() -> bool:
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / "cat.dicton.plist"
    plist_path.write_text(LAUNCHD_PLIST.format(exec_path=_exec_path()), encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    subprocess.run(["launchctl", "load", str(plist_path)], check=False)
    return True


def disable() -> bool:
    plist_path = Path.home() / "Library" / "LaunchAgents" / "cat.dicton.plist"
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink(missing_ok=True)
    return True
