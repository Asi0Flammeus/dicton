"""Service-manager helpers: systemd (Linux) and Windows daemon respawn.

Each public helper is a no-op (or ``False``) on platforms that don't apply
— callers never need to branch on the OS themselves.
"""

from __future__ import annotations

import os
import subprocess
import sys
from shutil import which


def systemd_unit_active() -> bool:
    if sys.platform != "linux" or not which("systemctl"):
        return False
    r = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", "dicton.service"],
        check=False,
    )
    return r.returncode == 0


def restart_systemd_unit() -> bool:
    if sys.platform != "linux" or not which("systemctl"):
        return False
    r = subprocess.run(
        ["systemctl", "--user", "restart", "dicton.service"],
        check=False,
    )
    return r.returncode == 0


def kill_stale_dicton() -> None:
    """Kill any *other* dicton.exe / dictonw.exe holding a shim open.

    Windows refuses to overwrite a running .exe, so a daemon launched
    via autostart (dictonw.exe) or a parallel ``dicton`` shell blocks
    the upgrade. We exclude our own PID — self-replacement is handled
    by the detached-helper path which waits for us to exit.
    """
    if sys.platform != "win32":
        return
    for image in ("dicton.exe", "dictonw.exe"):
        subprocess.run(
            ["taskkill", "/F", "/IM", image, "/FI", f"PID ne {os.getpid()}"],
            check=False,
            capture_output=True,
        )


def spawn_detached_upgrade(cmd: list[str], *, restart_daemon: bool) -> bool:
    """Launch a PowerShell window that waits for us to exit, then runs `cmd`.

    Self-replacement is impossible on Windows: the running dicton.exe
    holds an exclusive lock on the file uv wants to overwrite. The
    helper waits on our PID, then runs the upgrade once the lock drops.
    With ``restart_daemon=True`` it also kills any surviving dictonw.exe
    and ``Start-Process dictonw`` afterwards so the daemon is live again.

    Returns ``True`` if the upgrade was handed off to a detached helper
    (Windows only), ``False`` on platforms where the caller should run
    ``cmd`` itself.
    """
    if sys.platform != "win32":
        return False
    quoted = " ".join(_ps_quote(a) for a in cmd)
    restart_block = ""
    if restart_daemon:
        restart_block = (
            "if ($LASTEXITCODE -eq 0) { "
            "Write-Host ''; "
            "Write-Host 'Killing any surviving dictonw...' -ForegroundColor Cyan; "
            "taskkill /F /IM dictonw.exe 2>$null | Out-Null; "
            "Start-Sleep -Milliseconds 300; "
            "Write-Host 'Starting dictonw...' -ForegroundColor Cyan; "
            "Start-Process dictonw; "
            "Write-Host 'Daemon restarted.' -ForegroundColor Green "
            "} else { "
            "Write-Host 'Upgrade failed; daemon not restarted.' -ForegroundColor Red "
            "}; "
        )
    script = (
        f"$p = Get-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; "
        f"if ($p) {{ $p.WaitForExit() }}; Start-Sleep -Milliseconds 500; "
        f"Write-Host 'Running: {quoted}' -ForegroundColor Cyan; "
        f"{quoted}; "
        f"{restart_block}"
        f"Write-Host ''; Read-Host 'Press Enter to close'"
    )
    CREATE_NEW_CONSOLE = 0x00000010  # noqa: N806
    subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", script],
        creationflags=CREATE_NEW_CONSOLE,
        close_fds=True,
    )
    return True


def _ps_quote(s: str) -> str:
    if not s or any(c in s for c in " \t\"'"):
        return "'" + s.replace("'", "''") + "'"
    return s
