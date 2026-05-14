"""Autostart and platform helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import user_config_dir


def autostart_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/LaunchAgents/cat.dicton.plist"
    if sys.platform.startswith("win"):
        return (
            Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/dicton.cmd"
        )
    return Path(user_config_dir("systemd/user", appauthor=False)) / "dicton.service"


def install_autostart(command: str = "dicton") -> Path:
    path = autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        path.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict><key>Label</key><string>cat.dicton</string><key>ProgramArguments</key><array><string>{command}</string></array><key>RunAtLoad</key><true/></dict></plist>\n""")
    elif sys.platform.startswith("win"):
        path.write_text(f"@echo off\n{command}\n")
    else:
        path.write_text(
            f"[Unit]\nDescription=Dicton\n[Service]\nExecStart={command}\nRestart=on-failure\n[Install]\nWantedBy=default.target\n"
        )
    return path
